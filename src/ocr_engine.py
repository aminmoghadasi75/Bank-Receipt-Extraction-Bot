from pathlib import Path
from typing import Union, List, Optional
import numpy as np
from loguru import logger


class OCREngine:
    """Wrapper class around PaddleOCR for extracting text from Persian bank receipts."""

    def __init__(self, lang: str = "fa", use_angle_cls: bool = True, show_log: bool = False):
        self.lang = lang
        self.use_angle_cls = use_angle_cls
        self.show_log = show_log
        self._ocr_model = None

    def _get_ocr_model(self):
        """Lazy initialization of PaddleOCR model."""
        if self._ocr_model is None:
            try:
                import os
                os.environ["PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK"] = "True"
                from paddleocr import PaddleOCR
                logger.info(f"Initializing PaddleOCR with lang='{self.lang}'...")
                self._ocr_model = PaddleOCR(
                    use_angle_cls=False,
                    enable_mkldnn=False,
                    lang=self.lang
                )
            except Exception as e:
                logger.error(f"Failed to initialize PaddleOCR: {e}")
                raise RuntimeError(f"PaddleOCR initialization error: {e}")
        return self._ocr_model

    def extract_text(self, image_input: Union[np.ndarray, str, Path]) -> str:
        """Extract text lines from image array or path.

        Returns:
            Concatenated text string separated by newlines.
        """
        ocr = self._get_ocr_model()

        if isinstance(image_input, (str, Path)):
            image_arg = str(image_input)
        elif isinstance(image_input, np.ndarray):
            image_arg = image_input
        else:
            raise TypeError(f"Unsupported image input type: {type(image_input)}")

        logger.debug("Executing OCR text detection...")
        try:
            results = ocr.ocr(image_arg)
        except Exception as ocr_err:
            logger.error(f"PaddleOCR execution error: {ocr_err}")
            return ""

        if not results or results[0] is None:
            logger.warning("PaddleOCR returned no text results.")
            return ""

        extracted_lines: List[str] = []
        for res in results:
            if not res:
                continue
            for line in res:
                if len(line) >= 2 and isinstance(line[1], (list, tuple)):
                    text_str = line[1][0]
                    confidence = line[1][1]
                    if text_str and text_str.strip():
                        extracted_lines.append(text_str.strip())
                        logger.trace(f"OCR Detected line: '{text_str.strip()}' (Conf: {confidence:.2f})")

        concatenated_text = "\n".join(extracted_lines)
        logger.info(f"OCR extracted {len(extracted_lines)} text lines.")
        return concatenated_text
