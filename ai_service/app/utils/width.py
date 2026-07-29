"""Crack width calculation module."""

import os
import logging

import cv2
import numpy as np
from glob import glob
from numba import jit

from app.utils.fast_thin import fast_thin

logger = logging.getLogger(__name__)


@jit(nopython=True)
def _find_nonzero(img):
    """Count non-zero pixels in image regions."""
    coords = []
    for i in range(img.shape[0]):
        for j in range(img.shape[1]):
            if img[i, j] != 0:
                coords.append((i, j))
    return coords


def _measure_width_slices(image: np.ndarray, n_slices: int = 10) -> list:
    """Measure non-zero pixel count in horizontal slices of the image."""
    h, w = image.shape[:2]
    step_h = max(int(h / n_slices), 1)
    widths = []

    for j in range(1, h, step_h):
        roi = image[j : j + step_h, 0:w]
        widths.append(len(_find_nonzero(roi)))

    return widths


def width_calculator(path: str) -> None:
    """
    Calculate crack widths from segmented images and write crack_info_may.txt.

    Args:
        path: Processing directory (the 10m/ directory).
    """
    segmented_path = os.path.join(path, "small", "cropped_crack", "*.jpg")
    save_base = path.replace("10m", "")
    pci_dir = os.path.join(save_base, "pci")
    os.makedirs(pci_dir, exist_ok=True)

    output_file = os.path.join(pci_dir, "crack_info_may.txt")

    with open(output_file, "w") as f:
        for img_path in sorted(glob(segmented_path)):
            name = os.path.basename(img_path)
            parts = name.split("_")

            # Parse filename: {image_name}_{type}_{length/area}_segmented.jpg
            image_name = "_".join(parts[:-3])
            crack_type = parts[-3]
            measurement = "".join(parts[-2])

            image = cv2.imread(img_path)
            image = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
            img_inverted = cv2.bitwise_not(image)

            if crack_type in ("alr", "patching", "pothole"):
                f.write(f"{image_name},{crack_type},{measurement},high,0\n")
            else:
                if 0 in img_inverted:
                    thinned = fast_thin(image)
                    skeleton = cv2.subtract(255, thinned)

                    image_widths = _measure_width_slices(image)
                    skeleton_widths = _measure_width_slices(skeleton)

                    max_skel = max(skeleton_widths) if skeleton_widths else 0
                    max_img = max(image_widths) if image_widths else 0

                    if max_skel != 0:
                        width = float(max_img / max_skel)
                        if width < 6:
                            severity = "low"
                        elif width < 20:
                            severity = "med"
                        else:
                            severity = "high"
                        f.write(f"{image_name},{crack_type},{measurement},{severity},{width}\n")
                    else:
                        f.write(f"{image_name},{crack_type},{measurement},low,0\n")
                else:
                    f.write(f"{image_name},{crack_type},{measurement},low,0\n")

    logger.info(f"Width calculation results written to {output_file}")
