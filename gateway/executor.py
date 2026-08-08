import base64
import time
import logging
import asyncio
from typing import Optional, Dict, Any, Tuple
import httpx
from gateway.config import settings
from gateway.key_manager import APIKeyManager, KeyState
from gateway.models import BankReceiptData, OCRResponse
from gateway.validator import ResponseValidator, SYSTEM_OCR_PROMPT, RETRY_REPAIR_PROMPT
from gateway.cache import ReceiptCacheManager

logger = logging.getLogger("gemini_gateway.executor")


class GeminiResilientExecutor:
    """Core Resilient Executor managing key rotation, retries, failover, rate-limit auto-wait, and fallback handling."""

    def __init__(self, key_manager: APIKeyManager, cache_manager: Optional[ReceiptCacheManager] = None):
        self.key_manager = key_manager
        self.cache_manager = cache_manager or ReceiptCacheManager(ttl_seconds=settings.cache_ttl_seconds)
        self._concurrency_semaphore = asyncio.Semaphore(settings.concurrency_limit)

    async def execute_receipt_ocr(
        self,
        image_bytes: bytes,
        mime_type: str = "image/jpeg",
        max_retries: Optional[int] = None
    ) -> OCRResponse:
        """Executes bank receipt OCR with automatic caching, key failover, rate-limit auto-wait, and response validation."""
        start_time = time.time()
        
        # Set max_retries to cover at least all loaded keys
        total_keys_count = len(self.key_manager.keys)
        retries_limit = max_retries if max_retries is not None else max(settings.max_retries, total_keys_count * 2, 5)

        # 1. Check Cache
        image_hash = self.cache_manager.compute_image_hash(image_bytes)
        if settings.enable_cache:
            cached_data = self.cache_manager.get(image_hash)
            if cached_data:
                receipt = BankReceiptData(**cached_data)
                return OCRResponse(
                    success=True,
                    data=receipt,
                    cached=True,
                    used_account_id="CACHE_HIT",
                    attempts=0,
                    latency_seconds=round(time.time() - start_time, 3)
                )

        # 2. Acquire Concurrency Semaphore
        async with self._concurrency_semaphore:
            last_error: Optional[str] = None
            attempt = 0

            while attempt < retries_limit:
                attempt += 1
                key_state: Optional[KeyState] = await self.key_manager.get_best_key()

                # If no key is immediately available, check if keys are simply in temporary cooldown
                if not key_state:
                    metrics = await self.key_manager.get_all_metrics()
                    cooldown_keys = [m for m in metrics if m.cooldown_until and m.cooldown_until > time.time()]
                    
                    if cooldown_keys:
                        min_wait = min(m.cooldown_until - time.time() for m in cooldown_keys)
                        wait_seconds = max(1.0, min_wait + 1.0)
                        logger.info(
                            f"All available keys in COOLDOWN. Waiting {round(wait_seconds, 1)}s "
                            f"for key recovery before attempt #{attempt}..."
                        )
                        await asyncio.sleep(wait_seconds)
                        # Try selecting best key again after sleep
                        key_state = await self.key_manager.get_best_key()

                if not key_state:
                    error_msg = "No active Gemini API keys available in pool."
                    logger.error(error_msg)
                    return OCRResponse(
                        success=False,
                        error=error_msg,
                        attempts=attempt,
                        latency_seconds=round(time.time() - start_time, 3)
                    )

                logger.info(
                    f"[Attempt {attempt}/{retries_limit}] Selected key {key_state.account_id} "
                    f"({key_state.api_key_masked}) with score={round(key_state.get_score(time.time()), 2)}"
                )

                req_start = time.time()
                try:
                    raw_text, status_code, headers = await self._call_gemini_vision_api(
                        api_key=key_state.api_key,
                        image_bytes=image_bytes,
                        mime_type=mime_type,
                        system_instruction=SYSTEM_OCR_PROMPT
                    )
                    req_latency = time.time() - req_start

                    # 3. Handle Status Code Outcomes
                    if status_code == 200:
                        receipt, val_err = ResponseValidator.parse_and_validate(raw_text)

                        if not receipt:
                            logger.warning(f"Invalid JSON returned on attempt {attempt}: {val_err}. Retrying with repair prompt...")
                            repair_text, r_status, _ = await self._call_gemini_vision_api(
                                api_key=key_state.api_key,
                                image_bytes=image_bytes,
                                mime_type=mime_type,
                                system_instruction=RETRY_REPAIR_PROMPT
                            )
                            if r_status == 200:
                                receipt, val_err = ResponseValidator.parse_and_validate(repair_text)

                        if receipt:
                            await self.key_manager.record_success(key_state.account_id, req_latency)
                            if settings.enable_cache:
                                self.cache_manager.set(image_hash, receipt.model_dump())

                            return OCRResponse(
                                success=True,
                                data=receipt,
                                cached=False,
                                used_account_id=key_state.account_id,
                                attempts=attempt,
                                latency_seconds=round(time.time() - start_time, 3)
                            )
                        else:
                            last_error = f"Response validation failed: {val_err}"
                            await self.key_manager.record_general_failure(key_state.account_id, last_error)

                    elif status_code == 429:
                        retry_after_hdr = headers.get("retry-after") or headers.get("Retry-After")
                        retry_after_sec = int(retry_after_hdr) if retry_after_hdr and retry_after_hdr.isdigit() else None
                        
                        await self.key_manager.record_rate_limit(key_state.account_id, retry_after=retry_after_sec)
                        last_error = f"429 Resource Exhausted on {key_state.account_id}"
                        logger.warning(f"Failover triggered due to 429 on {key_state.account_id}. Selecting next best key...")

                    elif status_code in (401, 403):
                        await self.key_manager.record_auth_error(key_state.account_id, status_code)
                        last_error = f"{status_code} Unauthorized/Forbidden on {key_state.account_id}"
                        logger.error(f"Failover triggered due to Auth Error on {key_state.account_id}. Selecting next best key...")

                    else:
                        await self.key_manager.record_general_failure(key_state.account_id, f"HTTP {status_code}")
                        last_error = f"HTTP {status_code} error from Gemini API"
                        logger.warning(f"Failover triggered due to status {status_code} on {key_state.account_id}. Retrying...")

                except httpx.TimeoutException:
                    last_error = f"Timeout error calling Gemini API on key {key_state.account_id}"
                    await self.key_manager.record_general_failure(key_state.account_id, "Timeout")
                    logger.warning(f"Timeout on key {key_state.account_id}. Automatic failover executing...")

                except Exception as e:
                    last_error = f"Unhandled exception: {str(e)}"
                    await self.key_manager.record_general_failure(key_state.account_id, str(e))
                    logger.exception(f"Unexpected error executing request on key {key_state.account_id}: {e}")

                await asyncio.sleep(1.0)

            return OCRResponse(
                success=False,
                error=last_error or "Max retries exceeded without success.",
                attempts=attempt,
                latency_seconds=round(time.time() - start_time, 3)
            )

    async def _call_gemini_vision_api(
        self,
        api_key: str,
        image_bytes: bytes,
        mime_type: str,
        system_instruction: str
    ) -> Tuple[str, int, Dict[str, str]]:
        """Direct REST call to Gemini API using httpx."""
        b64_image = base64.b64encode(image_bytes).decode("utf-8")
        
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{settings.model_name}:generateContent?key={api_key}"
        
        payload = {
            "contents": [
                {
                    "parts": [
                        {"text": system_instruction},
                        {
                            "inline_data": {
                                "mime_type": mime_type,
                                "data": b64_image
                            }
                        }
                    ]
                }
            ],
            "generationConfig": {
                "temperature": 0.1,
                "response_mime_type": "application/json"
            }
        }

        async with httpx.AsyncClient(timeout=35.0) as client:
            response = await client.post(url, json=payload)
            headers = dict(response.headers)
            
            if response.status_code == 200:
                resp_json = response.json()
                try:
                    text_content = resp_json["candidates"][0]["content"]["parts"][0]["text"]
                    return text_content, 200, headers
                except (KeyError, IndexError) as parse_err:
                    logger.warning(f"Could not extract text from 200 response: {parse_err}")
                    return response.text, 200, headers
            else:
                return response.text, response.status_code, headers
