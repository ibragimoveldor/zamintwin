"""
PCI Pipeline Orchestrator.

Coordinates the full analysis pipeline. Models are loaded ONCE at startup
and reused across requests (unlike the old subprocess approach that loaded
models for each project).
"""

import os
import time
import logging

logger = logging.getLogger(__name__)


class PCIPipeline:
    """
    Orchestrates the PCI analysis pipeline.

    Models are loaded in __init__ and kept in memory.
    The run() method is called per-project and is stateless
    with respect to the pipeline itself.
    """

    def __init__(self, det_model_path: str, seg_model_path: str, dv_path: str, gpu_id: int = 0):
        self.dv_path = dv_path
        self.gpu_id = gpu_id

        # Load detection + segmentation models ONCE
        from app.detection.detector import CrackDetector
        self.detector = CrackDetector(det_model_path, seg_model_path, gpu_id)
        logger.info("Detection and segmentation models loaded")

    def run(self, images_dir: str) -> dict:
        """
        Run the full pipeline on a project's images directory.

        Args:
            images_dir: Absolute path to the project's images/ directory.

        Returns:
            Dict with elapsed time and status info.
        """
        tic = time.time()

        # Step 1: Preprocess - stack into 10m segments
        logger.info(f"Step 1/4: Preprocessing {images_dir}")
        from app.preprocessing.image_ops import image_10m
        image_10m(images_dir)

        processing_dir = images_dir.replace("images", "10m")

        # Step 2: Crack detection + segmentation
        logger.info("Step 2/4: Crack detection")
        self._run_detection(processing_dir)

        # Step 3: Width calculation
        logger.info("Step 3/4: Width calculation")
        from app.utils.width import width_calculator
        width_calculator(processing_dir)

        # Step 4: PCI evaluation
        logger.info("Step 4/4: PCI evaluation")
        from app.evaluation.pci_calculator import compute_pci
        compute_pci(processing_dir, self.dv_path)

        elapsed = time.time() - tic
        logger.info(f"Pipeline completed in {elapsed:.2f}s")

        return {"elapsed": elapsed, "output_dir": processing_dir.replace("10m", "")}

    def run_step(self, images_dir: str, step: str) -> dict:
        """Run a single pipeline step (for debugging/reprocessing)."""
        tic = time.time()
        processing_dir = images_dir.replace("images", "10m")

        if step == "preprocessing":
            from app.preprocessing.image_ops import image_10m
            image_10m(images_dir)

        elif step == "detection":
            self._run_detection(processing_dir)

        elif step == "width_calculation":
            from app.utils.width import width_calculator
            width_calculator(processing_dir)

        elif step == "pci_evaluation":
            from app.evaluation.pci_calculator import compute_pci
            compute_pci(processing_dir, self.dv_path)

        else:
            raise ValueError(f"Unknown step: {step}")

        return {"step": step, "elapsed": time.time() - tic}

    def _run_detection(self, processing_dir: str):
        """Run detection using the pre-loaded detector."""
        from app.preprocessing.image_ops import splitter_lscan, joiner

        imglist = splitter_lscan(processing_dir)
        for name in imglist:
            imgpath = os.path.join(processing_dir, "small", name)
            self.detector.process_image(imgpath)

        joiner(processing_dir, comparison=True)
