import time
import asyncio
import logging
from typing import Dict, List, Optional
from gateway.models import KeyStatus, APIKeyMetrics
from gateway.config import settings

logger = logging.getLogger("gemini_gateway.key_manager")


class KeyState:
    """Internal state model holding sensitive API key string along with its public metrics."""

    def __init__(self, account_id: str, api_key: str):
        self.account_id = account_id
        self.api_key = api_key
        self.status = KeyStatus.ACTIVE
        self.total_requests = 0
        self.successful_requests = 0
        self.failed_requests = 0
        self.rate_limit_errors = 0
        self.last_used_time: Optional[float] = None
        self.last_error_time: Optional[float] = None
        self.cooldown_until: Optional[float] = None
        self.average_response_time: float = 0.0
        self.consecutive_429_count: int = 0

    @property
    def api_key_masked(self) -> str:
        """Returns a masked version of the API key for safe logging (e.g., AIza...1234)."""
        if not self.api_key or len(self.api_key) < 8:
            return "****"
        return f"{self.api_key[:4]}...{self.api_key[-4:]}"

    def get_score(self, current_time: float) -> float:
        """Calculates dynamic score for intelligent key selection.
        
        Higher score = preferred key.
        Formula:
          Score = HealthScore + AvailabilityScore + LatencyScore - ErrorPenalty - UsagePenalty
        """
        # Health score (0..50): Ratio of successful requests
        if self.total_requests == 0:
            health_score = 50.0  # Fresh keys get full initial health score
        else:
            health_score = (self.successful_requests / self.total_requests) * 50.0

        # Availability / Recency score (0..30): Encourage even rotation by favoring keys used less recently
        if self.last_used_time is None:
            availability_score = 30.0
        else:
            time_since_used = current_time - self.last_used_time
            availability_score = min(30.0, time_since_used * 2.0)

        # Latency score (0..20): Prefer faster keys
        if self.average_response_time == 0.0:
            latency_score = 15.0
        else:
            # Benchmark 2 seconds latency as neutral
            latency_score = max(0.0, 20.0 - (self.average_response_time * 5.0))

        # Error penalty
        error_penalty = (self.rate_limit_errors * 10.0) + (self.failed_requests * 15.0) + (self.consecutive_429_count * 20.0)

        # Recent total usage penalty (to prevent single-key overloading)
        usage_penalty = self.total_requests * 0.5

        final_score = health_score + availability_score + latency_score - error_penalty - usage_penalty
        return final_score

    def to_metrics(self, current_time: float) -> APIKeyMetrics:
        """Converts key state to public APIKeyMetrics model."""
        return APIKeyMetrics(
            account_id=self.account_id,
            api_key_masked=self.api_key_masked,
            status=self.status,
            total_requests=self.total_requests,
            successful_requests=self.successful_requests,
            failed_requests=self.failed_requests,
            rate_limit_errors=self.rate_limit_errors,
            last_used_time=self.last_used_time,
            last_error_time=self.last_error_time,
            cooldown_until=self.cooldown_until,
            average_response_time=round(self.average_response_time, 3),
            consecutive_429_count=self.consecutive_429_count,
            score=round(self.get_score(current_time), 2)
        )


class APIKeyManager:
    """Manages the pool of Gemini API keys with smart rotation and cooldown logic."""

    def __init__(self, raw_api_keys: Optional[List[str]] = None):
        self._lock = asyncio.Lock()
        self.keys: Dict[str, KeyState] = {}
        
        keys_to_load = raw_api_keys if raw_api_keys is not None else settings.api_keys
        for idx, key_str in enumerate(keys_to_load, start=1):
            acc_id = f"account_{idx}"
            self.keys[acc_id] = KeyState(account_id=acc_id, api_key=key_str)
            logger.info(f"Loaded key {acc_id} ({self.keys[acc_id].api_key_masked}) into key pool.")

    async def get_best_key(self) -> Optional[KeyState]:
        """Selects the best available API key using the smart scoring algorithm."""
        async with self._lock:
            now = time.time()
            candidates: List[KeyState] = []

            for key_state in self.keys.values():
                # Check if key is disabled or permanently failed
                if key_state.status in (KeyStatus.DISABLED, KeyStatus.FAILED):
                    continue

                # Check if key is currently in cooldown
                if key_state.cooldown_until and key_state.cooldown_until > now:
                    continue
                
                # If cooldown period has passed, restore status to ACTIVE
                if key_state.status in (KeyStatus.COOLDOWN, KeyStatus.RATE_LIMITED):
                    logger.info(f"Key {key_state.account_id} recovered from cooldown. Restoring to ACTIVE.")
                    key_state.status = KeyStatus.ACTIVE
                    key_state.cooldown_until = None

                candidates.append(key_state)

            if not candidates:
                logger.warning("No active API keys available in the pool!")
                return None

            # Sort candidates by smart score in descending order
            best_candidate = max(candidates, key=lambda k: k.get_score(now))
            best_candidate.last_used_time = now
            best_candidate.total_requests += 1
            return best_candidate

    async def record_success(self, account_id: str, latency_seconds: float):
        """Record successful request for a key."""
        async with self._lock:
            if account_id in self.keys:
                k = self.keys[account_id]
                k.successful_requests += 1
                k.consecutive_429_count = 0
                
                # Update running average response time
                if k.average_response_time == 0.0:
                    k.average_response_time = latency_seconds
                else:
                    k.average_response_time = (k.average_response_time * 0.8) + (latency_seconds * 0.2)

    async def record_rate_limit(self, account_id: str, retry_after: Optional[int] = None):
        """Record 429 Resource Exhausted rate limit error and place key into cooldown."""
        async with self._lock:
            now = time.time()
            if account_id in self.keys:
                k = self.keys[account_id]
                k.rate_limit_errors += 1
                k.consecutive_429_count += 1
                k.last_error_time = now
                k.status = KeyStatus.COOLDOWN

                if retry_after and retry_after > 0:
                    cooldown_dur = retry_after
                else:
                    # Exponential backoff: 1st=60s, 2nd=300s (5m), 3rd+=900s (15m)
                    if k.consecutive_429_count == 1:
                        cooldown_dur = 60
                    elif k.consecutive_429_count == 2:
                        cooldown_dur = 300
                    else:
                        cooldown_dur = 900

                k.cooldown_until = now + cooldown_dur
                logger.warning(
                    f"Key {account_id} hit 429 Rate Limit (attempt #{k.consecutive_429_count}). "
                    f"Placed in COOLDOWN for {cooldown_dur}s until {time.strftime('%H:%M:%S', time.localtime(k.cooldown_until))}."
                )

    async def record_auth_error(self, account_id: str, status_code: int):
        """Record 401/403 auth error and permanently disable key pending manual review."""
        async with self._lock:
            now = time.time()
            if account_id in self.keys:
                k = self.keys[account_id]
                k.failed_requests += 1
                k.last_error_time = now
                k.status = KeyStatus.DISABLED
                logger.error(f"Key {account_id} encountered {status_code} Auth Error! Marked as DISABLED.")

    async def record_general_failure(self, account_id: str, error_msg: str):
        """Record 5xx server error or timeout."""
        async with self._lock:
            now = time.time()
            if account_id in self.keys:
                k = self.keys[account_id]
                k.failed_requests += 1
                k.last_error_time = now
                logger.warning(f"Key {account_id} failed with error: {error_msg}")

    async def reset_key_status(self, account_id: str) -> bool:
        """Manually re-enable or reset a key's status to ACTIVE."""
        async with self._lock:
            if account_id in self.keys:
                k = self.keys[account_id]
                k.status = KeyStatus.ACTIVE
                k.cooldown_until = None
                k.consecutive_429_count = 0
                logger.info(f"Key {account_id} manually reset to ACTIVE.")
                return True
            return False

    async def get_all_metrics(self) -> List[APIKeyMetrics]:
        """Returns metrics for all managed keys."""
        async with self._lock:
            now = time.time()
            return [k.to_metrics(now) for k in self.keys.values()]
