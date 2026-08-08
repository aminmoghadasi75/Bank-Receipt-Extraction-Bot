import os
from typing import List
from dotenv import load_dotenv

load_dotenv()

class GatewayConfig:
    """System configuration for Gemini API Multi-Account Gateway."""

    def __init__(self):
        self.model_name: str = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
        self.max_retries: int = int(os.getenv("MAX_RETRIES", "3"))
        self.concurrency_limit: int = int(os.getenv("CONCURRENCY_LIMIT", "5"))
        self.db_path: str = os.getenv("DATABASE_URL", "sqlite+aiosqlite:///gateway.db")
        self.cache_ttl_seconds: int = int(os.getenv("CACHE_TTL_SECONDS", "86400")) # 24 hours
        self.enable_cache: bool = os.getenv("ENABLE_CACHE", "true").lower() == "true"
        self.base_cooldown_seconds: int = int(os.getenv("BASE_COOLDOWN_SECONDS", "60"))
        
        # Load API keys from GEMINI_API_KEYS (comma separated) or GEMINI_API_KEY_*
        self.api_keys: List[str] = self._parse_api_keys()

    def _parse_api_keys(self) -> List[str]:
        keys = []
        raw_keys = os.getenv("GEMINI_API_KEYS", "")
        if raw_keys.strip():
            for k in raw_keys.split(","):
                k_clean = k.strip()
                if k_clean and k_clean not in keys:
                    keys.append(k_clean)

        # Also scan individual GEMINI_API_KEY_1, GEMINI_API_KEY_2, etc.
        idx = 1
        while True:
            k = os.getenv(f"GEMINI_API_KEY_{idx}")
            if not k:
                # Also check without index 1 fallback if GEMINI_API_KEY exists
                if idx == 1:
                    single_key = os.getenv("GEMINI_API_KEY")
                    if single_key and single_key.strip() and single_key.strip() not in keys:
                        keys.append(single_key.strip())
                break
            k_clean = k.strip()
            if k_clean and k_clean not in keys:
                keys.append(k_clean)
            idx += 1

        return keys


settings = GatewayConfig()
