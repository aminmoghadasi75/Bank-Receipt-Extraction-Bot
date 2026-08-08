from pathlib import Path
from typing import Union
import cv2
import numpy as np
from loguru import logger


class ImageProcessor:
    """Class to load and preprocess bank receipt images for optimal OCR accuracy."""

    def __init__(self, apply_clahe: bool = True, gaussian_kernel: tuple = (3, 3)):
        self.apply_clahe = apply_clahe
        self.gaussian_kernel = gaussian_kernel

    def load_image(self, image_input: Union[str, Path, np.ndarray]) -> np.ndarray:
        """Load image safely handling Unicode paths on Windows/Linux."""
        if isinstance(image_input, np.ndarray):
            return image_input

        path = Path(image_input)
        if not path.exists():
            raise FileNotFoundError(f"Image path does not exist: {path}")

        # Read binary data first to safely handle non-ASCII/Unicode file paths
        img_bytes = np.fromfile(str(path), dtype=np.uint8)
        img = cv2.imdecode(img_bytes, cv2.IMREAD_COLOR)

        if img is None:
            raise ValueError(f"Failed to decode image at path: {path}")

        return img

    def preprocess(self, image_input: Union[str, Path, np.ndarray]) -> np.ndarray:
        """Process input image: BGR -> Grayscale -> Blur -> CLAHE/Thresholding.

        Returns processed numpy array image (RGB or Grayscale).
        """
        img = self.load_image(image_input)

        # Convert to Grayscale if image has multiple channels
        if len(img.shape) == 3:
            gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        else:
            gray = img.copy()

        # Gaussian Blur to noise reduction
        blurred = cv2.GaussianBlur(gray, self.gaussian_kernel, 0)

        # Contrast Enhancement using CLAHE (Contrast Limited Adaptive Histogram Equalization)
        if self.apply_clahe:
            clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
            enhanced = clahe.apply(blurred)
        else:
            enhanced = blurred

        # Optional sharpening
        sharpen_kernel = np.array([[0, -1, 0], [-1, 5, -1], [0, -1, 0]], dtype=np.float32)
        sharpened = cv2.filter2D(enhanced, -1, sharpen_kernel)

        # Convert back to 3 channels (BGR) since PaddleOCR expects 3-channel image array
        processed_bgr = cv2.cvtColor(sharpened, cv2.COLOR_GRAY2BGR)

        logger.debug(f"Image preprocessing finished. Dimensions: {processed_bgr.shape}")
        return processed_bgr
