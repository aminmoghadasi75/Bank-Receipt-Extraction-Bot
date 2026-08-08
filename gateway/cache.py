import hashlib
import time
import logging
from typing import Optional, Dict, Any

logger = logging.getLogger("gemini_gateway.cache")


class ReceiptCacheManager:
    """In-Memory cache manager with SHA-256 image hash lookup."""

    def __init__(self, ttl_seconds: int = 86400):
        self.ttl_seconds = ttl_seconds
        self._cache: Dict[str, Dict[str, Any]] = {}

    @staticmethod
    def compute_image_hash(image_bytes: bytes) -> str:
        """Compute SHA-256 hash of raw receipt image bytes."""
        return hashlib.sha256(image_bytes).hexdigest()

    def get(self, image_hash: str) -> Optional[Dict[str, Any]]:
        """Retrieve cached result if valid and not expired."""
        if image_hash in self._cache:
            entry = self._cache[image_hash]
            if time.time() < entry["expires_at"]:
                logger.info(f"Cache HIT for image hash {image_hash[:10]}...")
                return entry["data"]
            else:
                logger.info(f"Cache entry EXPIRED for image hash {image_hash[:10]}...")
                del self._cache[image_hash]
        return None

    def set(self, image_hash: str, data: Dict[str, Any]):
        """Store OCR result in cache."""
        self._cache[image_hash] = {
            "data": data,
            "expires_at": time.time() + self.ttl_seconds,
            "created_at": time.time()
        }
        logger.info(f"Cached result for image hash {image_hash[:10]}... (TTL: {self.ttl_seconds}s)")

    def clear(self):
        """Clear all cache entries."""
        self._cache.clear()
