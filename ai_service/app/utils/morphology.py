"""Morphological operations for crack segmentation enhancement."""

import math
import cv2
import numpy as np
from numba import jit


@jit(nopython=True)
def find_nonzero_pixels(img):
    """Find all non-zero pixel coordinates in a grayscale image."""
    height, width = img.shape[:2]
    coords = []
    for i in range(height):
        for j in range(width):
            if img[i, j] != 0:
                coords.append((i, j))
    return coords


def connect_nearby_cracks(img: np.ndarray, max_distance: float = 10.0) -> np.ndarray:
    """
    Connect nearby crack pixels by drawing lines between close non-zero points.
    Then apply morphological operations to clean up.
    """
    coords = find_nonzero_pixels(img)

    for i in range(1, len(coords)):
        p1, p2 = coords[i - 1], coords[i]
        distance = math.sqrt((p2[0] - p1[0]) ** 2 + (p2[1] - p1[1]) ** 2)
        if distance < max_distance:
            cv2.line(img, (p1[1], p1[0]), (p2[1], p2[0]), (255, 0, 0), 2)

    kernel_large = np.ones((8, 8), np.uint8)
    kernel_small = np.ones((2, 2), np.uint8)
    dilated = cv2.dilate(img, kernel_large, iterations=1)
    eroded = cv2.erode(dilated, kernel_large, iterations=1)
    opened = cv2.morphologyEx(eroded, cv2.MORPH_OPEN, kernel_small)

    return opened
