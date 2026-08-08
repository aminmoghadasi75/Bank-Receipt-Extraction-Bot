import json
import asyncio
from pathlib import Path
from typing import Dict, Any, Optional
from loguru import logger

from gateway.key_manager import APIKeyManager
from gateway.cache import ReceiptCacheManager
from gateway.executor import GeminiResilientExecutor


class LLMExtractor:
    """Extracts structured Iranian bank receipt JSON using Gemini API Multi-Account Gateway."""

    def __init__(self, api_key: Optional[str] = None, model_name: Optional[str] = None):
        # Instantiate Multi-Account Key Manager and Executor
        self.key_manager = APIKeyManager()
        self.cache_manager = ReceiptCacheManager()
        self.executor = GeminiResilientExecutor(key_manager=self.key_manager, cache_manager=self.cache_manager)

    def extract_structured_data_from_image(self, image_path: Path) -> Dict[str, Any]:
        """Pass raw receipt image to Gemini Multi-Account Gateway and return parsed dictionary.

        Args:
            image_path: Path to the receipt image.

        Returns:
            Dictionary containing extracted receipt fields.
        """
        img_path = Path(image_path)
        if not img_path.exists():
            logger.error(f"Image path does not exist: {img_path}")
            return {}

        try:
            with open(img_path, "rb") as f:
                image_bytes = f.read()
        except Exception as e:
            logger.error(f"Failed to read image bytes from '{img_path}': {e}")
            return {}

        mime_type = "image/jpeg"
        if img_path.suffix.lower() == ".png":
            mime_type = "image/png"
        elif img_path.suffix.lower() in (".webp",):
            mime_type = "image/webp"

        logger.info(f"Submitting '{img_path.name}' to Gemini Multi-Account Gateway...")

        # Run async executor synchronously
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            ocr_response = loop.run_until_complete(
                self.executor.execute_receipt_ocr(image_bytes=image_bytes, mime_type=mime_type)
            )
        finally:
            loop.close()

        if ocr_response.success and ocr_response.data:
            logger.info(
                f"[{img_path.name}] Gateway succeeded via account '{ocr_response.used_account_id}' "
                f"in {ocr_response.latency_seconds}s (Attempts: {ocr_response.attempts}, Cached: {ocr_response.cached})."
            )
            return ocr_response.data.model_dump()
        else:
            logger.warning(f"[{img_path.name}] Gateway extraction failed: {ocr_response.error}")
            return {}

    def extract_structured_data(self, ocr_text: str) -> Dict[str, Any]:
        """Legacy text extractor compatibility method."""
        if not ocr_text or not ocr_text.strip():
            return {}
        return {}
