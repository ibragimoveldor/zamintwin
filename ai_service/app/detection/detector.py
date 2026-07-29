"""
Crack detection module.

Combines YOLO object detection with UNet segmentation for comprehensive
crack analysis. Detects: horizontal/vertical cracks, alligator cracking,
patching, potholes, and manholes.
"""

import os
import logging
import pathlib

import cv2
import torch
import numpy as np
from PIL import Image
from glob import glob
from collections import OrderedDict
from skimage import measure
from torchvision import transforms

logger = logging.getLogger(__name__)

# Class colors for visualization
CLASS_COLORS = {
    "horizontal": (0, 255, 0),
    "vertical": (255, 0, 0),
    "alr": (0, 0, 255),
    "patching": (0, 255, 255),
    "manhole": (192, 192, 192),
    "pothole": (255, 0, 0),
}
# os.environ["HF_HUB_OFFLINE"] = "1"
# os.environ["TRANSFORMERS_OFFLINE"] = "1"


class SegmentationModel:
    """UNet-based crack segmentation model."""

    def __init__(self, model_path: str):
        
        # Temporarily allow network-free loading
        
        import segmentation_models_pytorch as smp
        
        
        model = smp.Unet(
            encoder_name="resnet101",
            encoder_weights= None, # "imagenet",
            decoder_attention_type="scse",
            in_channels=3,
            classes=1,
        )
        state_dict = torch.load(model_path, weights_only=False)
        new_state_dict = OrderedDict((k[7:], v) for k, v in state_dict.items())
        model.load_state_dict(new_state_dict)
        model.eval()
        self.model = model

    def segment_patch(self, patch: Image.Image) -> np.ndarray:
        """Segment a single image patch."""
        preprocess = transforms.Compose([
            transforms.Resize((1024, 1024)),
            transforms.ToTensor(),
        ])
        input_batch = preprocess(patch).unsqueeze(0)

        with torch.no_grad():
            prediction = self.model(input_batch)
            prediction = torch.sigmoid(prediction)
            mask = (prediction > 0.4).squeeze().cpu().numpy()

        return (mask * 255).astype("uint8")


class CrackDetector:
    """Combined YOLO detection + UNet segmentation pipeline."""

    def __init__(self, det_model_path: str, seg_model_path: str, gpu_id: int = 0):
        from ultralytics import YOLO

        self.device = f"cuda:{gpu_id}"
        self.det_model = YOLO(det_model_path).to(self.device)
        self.seg_model = SegmentationModel(seg_model_path)

    def process_image(self, image_path: str, thresh: float = 0.25) -> None:
        """Run full detection + segmentation on a single image."""
        image = Image.open(image_path)
        if image.size != (2048, 2048):
            image = image.resize((2048, 2048), Image.LANCZOS)
        image_np = np.array(image)

        # Segment
        mask = self._segment_image(image_np)

        # Detect objects
        detections = self._detect_objects(image_np)

        # Combine mask and detections
        combined = self._combine_mask_and_detections(mask, detections)
        crack_bboxes = self._extract_bounding_boxes(combined)
        all_detections = detections + crack_bboxes

        # Save visualization
        vis_image = self._visualize(image_np.copy(), mask, detections, thresh)
        cv2.imwrite(image_path, vis_image)

        # Save cropped detections for width calculation
        self._save_crops(
            image_np.copy(), mask, all_detections, thresh,
            os.path.dirname(image_path), os.path.basename(image_path),
        )

    def _segment_image(self, image: np.ndarray) -> np.ndarray:
        """Segment image using sliding window patches."""
        patch_size = 1024
        h, w = image.shape[:2]
        final_mask = np.zeros((h, w), dtype="uint8")

        for y in range(0, h, patch_size):
            for x in range(0, w, patch_size):
                patch = Image.fromarray(image[y : y + patch_size, x : x + patch_size])
                seg_patch = self.seg_model.segment_patch(patch)
                final_mask[y : y + patch_size, x : x + patch_size] = seg_patch

        return final_mask

    def _detect_objects(self, image: np.ndarray) -> list:
        """Run YOLO detection."""
        results = self.det_model.predict(image)
        detections = []
        for result in results:
            boxes = result.boxes.xyxy.cpu().numpy()
            confs = result.boxes.conf.cpu().numpy()
            cls_ids = result.boxes.cls.cpu().numpy()
            labels = [self.det_model.names[int(c)] for c in cls_ids]

            for box, conf, cls_id, label in zip(boxes, confs, cls_ids, labels):
                detections.append([box[0], box[1], box[2], box[3], conf, label])

        return detections

    def _combine_mask_and_detections(self, mask: np.ndarray, detections: list) -> np.ndarray:
        """Remove patching/alr regions from segmentation mask."""
        image_with_bboxes = cv2.cvtColor(mask, cv2.COLOR_GRAY2BGR)

        patch_alr_bboxes = [
            (int(d[0]), int(d[1]), int(d[2]), int(d[3]))
            for d in detections
            if d[5] in ("patching", "alr")
        ]

        for x1, y1, x2, y2 in patch_alr_bboxes:
            image_with_bboxes[y1:y2, x1:x2] = [0, 0, 0]

        h, w = image_with_bboxes.shape[:2]
        bbox_mask = np.zeros((h, w), dtype=np.uint8)
        for x1, y1, x2, y2 in patch_alr_bboxes:
            bbox_mask[y1:y2, x1:x2] = 1

        outside_mask = 1 - bbox_mask
        seg_color = cv2.cvtColor(cv2.resize(mask, (w, h)), cv2.COLOR_GRAY2BGR)

        final = image_with_bboxes.copy()
        final[outside_mask == 1] = seg_color[outside_mask == 1]
        return final

    def _extract_bounding_boxes(self, combined: np.ndarray, min_area: int = 300) -> list:
        """Extract connected component bounding boxes from combined image."""
        gray = cv2.cvtColor(combined, cv2.COLOR_BGR2GRAY)
        labels = measure.label(gray, connectivity=2)

        bboxes = []
        for label_val in np.unique(labels):
            if label_val == 0:
                continue
            coords = np.column_stack(np.where(labels == label_val))
            y_min, x_min = coords.min(axis=0)
            y_max, x_max = coords.max(axis=0)
            area = (x_max - x_min + 1) * (y_max - y_min + 1)
            if area >= min_area:
                bboxes.append([x_min, y_min, x_max, y_max, 0.5, "vertical"])

        return bboxes

    def _visualize(self, im: np.ndarray, mask: np.ndarray, dets: list, thresh: float) -> np.ndarray:
        """Create visualization with mask overlay and detection boxes."""
        colored_mask = np.zeros_like(im)
        colored_mask[mask > 0] = [0, 255, 0]
        blended = cv2.addWeighted(im, 1, colored_mask, 0.5, 0)

        for det in dets:
            bbox = tuple(int(np.round(x)) for x in det[:4])
            score, class_name = det[4], det[5]
            if score >= thresh:
                color = CLASS_COLORS.get(class_name, (0, 0, 0))
                cv2.rectangle(blended, bbox[0:2], bbox[2:4], color, -1)

        return blended

    def _save_crops(self, im: np.ndarray, mask: np.ndarray, dets: list, thresh: float, path: str, imgname: str):
        """Save cropped detections for width calculation."""
        crop_dir = os.path.join(path, "cropped_crack")
        os.makedirs(crop_dir, exist_ok=True)

        stem = imgname[:-6] if len(imgname) > 6 else imgname.split(".")[0]

        for det in dets:
            bbox = tuple(int(np.round(x)) for x in det[:4])
            score, class_name = det[4], det[5]

            if score < thresh:
                continue

            if class_name == "vertical":
                length = bbox[2] - bbox[0]
                if length > 100:
                    crop = mask[bbox[1] : bbox[3], bbox[0] : bbox[2]]
                    cv2.imwrite(f"{crop_dir}/{stem}_trans_{length}_segmented.jpg", crop)

            elif class_name == "horizontal":
                length = bbox[3] - bbox[1]
                if length >= 30:
                    crop = mask[bbox[1] : bbox[3], bbox[0] : bbox[2]]
                    cv2.imwrite(f"{crop_dir}/{stem}_crack_{length}_segmented.jpg", crop)

            elif class_name == "alr":
                area = (bbox[3] - bbox[1]) * (bbox[2] - bbox[0])
                if area > 90:
                    crop = im[bbox[1] : bbox[3], bbox[0] : bbox[2]]
                    cv2.imwrite(f"{crop_dir}/{stem}_alr_{area}_segmented.jpg", crop)

            elif class_name == "patching":
                area = (bbox[3] - bbox[1]) * (bbox[2] - bbox[0])
                if area > 90:
                    crop = im[bbox[1] : bbox[3], bbox[0] : bbox[2]]
                    cv2.imwrite(f"{crop_dir}/{stem}_patching_{area}_segmented.jpg", crop)

            elif class_name == "pothole":
                area = (bbox[3] - bbox[1]) * (bbox[2] - bbox[0])
                if area > 90:
                    crop = im[bbox[1] : bbox[3], bbox[0] : bbox[2]]
                    cv2.imwrite(f"{crop_dir}/{stem}_pothole_{area}_segmented.jpg", crop)


def crack_detect(path_image: str, path_det_model: str, path_seg_model: str, gpuid: int = 0):
    """
    Main entry point for crack detection.
    Splits images, runs detection, and joins results.
    """
    from app.preprocessing.image_ops import splitter_lscan, joiner

    detector = CrackDetector(path_det_model, path_seg_model, gpuid)
    imglist = splitter_lscan(path_image)

    for name in imglist:
        imgpath = os.path.join(path_image, "small", name)
        detector.process_image(imgpath)

    joiner(path_image, comparison=True)
    logger.info("Crack detection completed")
