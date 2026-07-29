"""
Image preprocessing operations.

Handles image splitting into patches, joining results back,
and creating 10-meter segments from line-scan images.
"""

import os
import logging

import cv2
import numpy as np
from PIL import Image
from glob import glob
from pathlib import Path

logger = logging.getLogger(__name__)


# def image_10m(images_dir: str, resize_size: tuple = (2048, 2048), overlap_height: int = 1024):
#     """
#     Resize images and stack them vertically with overlap.
#     Save the stacked image every 10 images.

#     Args:
#         images_dir: Directory containing the source images.
#         resize_size: Target size for each image (width, height).
#         overlap_height: Overlap between stacked images in pixels.
#     """
#     images = []

#     image_files = sorted(os.listdir(images_dir))
#     for image_file in image_files:
#         if image_file.lower().endswith((".jpg", ".jpeg", ".png")):
#             image_path = os.path.join(images_dir, image_file)
#             image = cv2.imread(image_path)
#             if image is not None:
#                 resized_image = cv2.resize(image, resize_size)
#                 images.append((image_file, resized_image))
#             else:
#                 logger.warning(f"Failed to load {image_file}")

#     # Output to sibling '10m' directory
#     parent_dir = os.path.dirname(images_dir.rstrip("/"))
#     output_dir = os.path.join(parent_dir, "10m")
#     os.makedirs(output_dir, exist_ok=True)

#     # Process in chunks of 10
#     for i in range(0, len(images), 10):
#         chunk = images[i : i + 10]

#         if len(chunk) < 10:
#             blank_image = np.zeros(resize_size + (3,), dtype=np.uint8)
#             chunk.extend([("blank.jpg", blank_image)] * (10 - len(chunk)))

#         base_filename = os.path.splitext(chunk[0][0])[0]
#         output_path = os.path.join(output_dir, f"{base_filename}.jpg")

#         final_image = chunk[0][1][:overlap_height]
#         for _, image in chunk[1:]:
#             overlap_part = image[:overlap_height]
#             final_image = np.vstack((overlap_part, final_image))

#         cv2.imwrite(output_path, final_image)
#     logger.info(f"Created {len(images) // 10 + 1} stacked images in {output_dir}")

def image_10m(images_dir: str, resize_size: tuple = (4096, 2048), images_per_stack: int = 5):
    """
    Resize images and stack them vertically without overlap.
    Save the stacked image every 5 images. If fewer than 5 remain,
    blank images are used to complete the stack.

    Args:
        images_dir: Directory containing the source images.
        resize_size: Target size for each image (width, height).
        images_per_stack: Number of images to stack vertically.
    """
    images = []

    image_files = sorted(os.listdir(images_dir))
    for image_file in image_files:
        if image_file.lower().endswith((".jpg", ".jpeg", ".png")):
            image_path = os.path.join(images_dir, image_file)
            image = cv2.imread(image_path)
            if image is not None:
                resized_image = cv2.resize(image, resize_size)
                images.append((image_file, resized_image))
            else:
                logger.warning(f"Failed to load {image_file}")

    # Output to sibling '10m' directory
    parent_dir = os.path.dirname(images_dir.rstrip("/"))
    output_dir = os.path.join(parent_dir, "10m")
    os.makedirs(output_dir, exist_ok=True)

    # Process in chunks of images_per_stack
    for i in range(0, len(images), images_per_stack):
        chunk = images[i : i + images_per_stack]

        if len(chunk) < images_per_stack:
            blank_image = np.zeros(resize_size[::-1] + (3,), dtype=np.uint8)  # (height, width, channels)
            chunk.extend([("blank.jpg", blank_image)] * (images_per_stack - len(chunk)))

        base_filename = os.path.splitext(chunk[0][0])[0]
        output_path = os.path.join(output_dir, f"{base_filename}.jpg")

        # Stack vertically in reverse order (no overlap)
        final_image = np.vstack([img for _, img in reversed(chunk)])

        cv2.imwrite(output_path, final_image)
        logger.info(f"Saved: {output_path} (shape: {final_image.shape})")

    logger.info(f"Created {len(images) // images_per_stack + 1} stacked images in {output_dir}")
def splitter_lscan(path: str) -> list:
    """
    Split line-scan images into smaller patches (1 row × 5 cols).

    Args:
        path: Directory containing the source images.

    Returns:
        Sorted list of patch filenames.
    """
    output_path = os.path.join(path, "small/")
    os.makedirs(output_path, exist_ok=True)
    imglist = []

    for image_file in glob(f"{path}/*.jpg"):
        im = Image.open(image_file)
        im_width, im_height = im.size
        rows, cols = 1, 5
        row_width = int(im_width / rows) - 1
        row_height = int(im_height / cols)

        for i in range(cols):
            for j in range(rows):
                box = (
                    j * row_width,
                    i * row_height,
                    j * row_width + row_width,
                    i * row_height + row_height,
                )
                patch = im.crop(box)
                stem = os.path.splitext(os.path.basename(image_file))[0]
                patch_name = f"{stem}_{i * rows + j}.jpg"
                patch.save(os.path.join(output_path, patch_name))
                imglist.append(patch_name)

    imglist.sort(key=lambda f: int("".join(filter(str.isdigit, f))))
    return imglist


def joiner(path: str, comparison: bool = False):
    """
    Rejoin small patches back into full images and create result visualizations.

    Args:
        path: Processing directory containing 'small/' subdirectory.
        comparison: If True, create side-by-side original vs result image.
    """
    path_small = os.path.join(path, "small/")
    save_path = path.replace("10m", "")
    path_res = os.path.join(save_path, "result/")
    os.makedirs(path_res, exist_ok=True)

    for im_path in glob(f"{path}/*.jpg"):
        imgname = os.path.splitext(os.path.basename(im_path))[0]

        # Reconstruct: 5 patches stacked vertically (2048x2048 each)
        img_res = np.zeros((2048 * 5, 2048, 3), dtype=np.uint8)

        for b in range(5):
            small_img_path = os.path.join(path_small, f"{imgname}_{b}.jpg")
            if os.path.exists(small_img_path):
                patch = cv2.imread(small_img_path)
                img_res[b * 2048 : (b + 1) * 2048, :] = patch
            else:
                logger.warning(f"Missing patch: {small_img_path}")

        if comparison:
            img_org = cv2.imread(im_path)
            k = 4
            w = int(2048 / k)
            h = int(2048 * 5 / k)
            img_org_scaled = cv2.resize(img_org, (w, h), interpolation=cv2.INTER_AREA)
            img_res_scaled = cv2.resize(img_res, (w, h), interpolation=cv2.INTER_AREA)

            pad = np.zeros((h, 10, 3), dtype=np.uint8)
            pad[:] = (255, 0, 0)

            h_img = cv2.hconcat([img_org_scaled, pad, img_res_scaled])
            output_path = os.path.join(path_res, f"{imgname}.jpg")
            h_img_rgb = h_img[:, :, ::-1]
            Image.fromarray(h_img_rgb.astype("uint8"), "RGB").save(
                output_path, format="JPEG", quality=100
            )
        else:
            output_path = os.path.join(path_res, f"{imgname}_joined.jpg")
            cv2.imwrite(output_path, img_res)
