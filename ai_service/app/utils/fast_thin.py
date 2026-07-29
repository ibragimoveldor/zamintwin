"""Fast morphological thinning for crack skeletonization."""

import cv2
import numpy as np
from numba import jit


def fast_thin(img_ori: np.ndarray) -> np.ndarray:
    """Apply fast thinning algorithm to produce skeleton."""
    img = _morphology(img_ori)
    _clean_corners(img)
    _erase_two_by_twos(img)
    _erase_ladders(img)
    return img


def _morphology(img: np.ndarray) -> np.ndarray:
    """Iterative morphological thinning until convergence."""
    _, img = cv2.threshold(img, 100, 255, cv2.THRESH_BINARY_INV)
    kernel = cv2.getStructuringElement(cv2.MORPH_CROSS, (3, 3))

    while True:
        last_img = img.copy()
        ero = cv2.erode(img, kernel, iterations=1)
        dil = cv2.dilate(ero, kernel, iterations=1)
        img -= dil
        img += ero
        if cv2.compare(img, last_img, cv2.CMP_EQ).all():
            break

    _, img = cv2.threshold(img, 100, 255, cv2.THRESH_BINARY_INV)
    return img


@jit(nopython=True)
def _clean_corners(img):
    """Set image borders to background (255)."""
    h, w = img.shape[:2]
    bg = 255
    img[0:h, 0] = bg
    img[0, 0:w] = bg
    img[0:h, w - 1] = bg
    img[h - 1, 0:w] = bg


@jit(nopython=True)
def _erase_two_by_twos(img):
    """Remove 2x2 foreground blocks."""
    h, w = img.shape[:2]
    obj, bg = 0, 255
    for y in range(1, h - 2):
        for x in range(1, w - 2):
            c1 = img[y, x]
            c2 = img[y, x + 1]
            c3 = img[y + 1, x]
            c4 = img[y + 1, x + 1]
            if c1 == obj and c2 == obj and c3 == obj and c4 == obj:
                if img[y - 1, x - 1] != obj:
                    img[y, x] = bg
                elif img[y - 1, x + 2] != obj:
                    img[y, x + 1] = bg
                elif img[y + 2, x - 1] != obj:
                    img[y + 1, x] = bg
                elif img[y + 2, x + 2] != obj:
                    img[y + 1, x + 1] = bg


@jit(nopython=True)
def _erase_ladders(img):
    """Remove ladder-like artifacts from thinned image."""
    h, w = img.shape[:2]
    obj, bg = 0, 255
    m1 = [[255, 0, 7], [0, 0, 7], [7, 7, 255]]
    m2 = [[7, 0, 255], [7, 0, 0], [255, 7, 7]]
    m3 = [[7, 7, 255], [0, 0, 7], [255, 0, 7]]
    m4 = [[255, 7, 7], [7, 0, 0], [7, 0, 255]]
    masks = [m1, m2, m3, m4]

    for y in range(1, h - 1):
        for x in range(1, w - 1):
            if img[y, x] != obj:
                continue
            p = [
                [img[y - 1, x - 1], img[y - 1, x], img[y - 1, x + 1]],
                [img[y, x - 1], img[y, x], img[y, x + 1]],
                [img[y + 1, x - 1], img[y + 1, x], img[y + 1, x + 1]],
            ]
            for m in masks:
                match = True
                for i in range(3):
                    for j in range(3):
                        if m[i][j] != 7 and m[i][j] != p[i][j]:
                            match = False
                if match:
                    img[y, x] = bg
                    break
