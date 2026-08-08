import pytest
from unittest.mock import AsyncMock, patch
from gateway.key_manager import APIKeyManager
from gateway.executor import GeminiResilientExecutor
from gateway.cache import ReceiptCacheManager


@pytest.mark.asyncio
async def test_failover_on_429_rate_limit():
    keys = ["KEY_FAILOVER_1", "KEY_FAILOVER_2"]
    key_manager = APIKeyManager(raw_api_keys=keys)
    cache_manager = ReceiptCacheManager()
    executor = GeminiResilientExecutor(key_manager=key_manager, cache_manager=cache_manager)

    mock_valid_json = """
    {
        "reference_number": "REF12345",
        "amount": 500000.0,
        "currency": "IRR",
        "bank_name": "Melli",
        "transaction_status": "SUCCESS"
    }
    """

    # Mock _call_gemini_vision_api to return 429 for account_1, and 200 for account_2
    async def mock_call_api(api_key, image_bytes, mime_type, system_instruction):
        if api_key == "KEY_FAILOVER_1":
            return "429 RESOURCE_EXHAUSTED", 429, {}
        elif api_key == "KEY_FAILOVER_2":
            return mock_valid_json, 200, {}
        return "Unknown", 500, {}

    with patch.object(executor, "_call_gemini_vision_api", side_effect=mock_call_api):
        dummy_image = b"test_receipt_image_content"
        response = await executor.execute_receipt_ocr(image_bytes=dummy_image, max_retries=3)

        assert response.success is True
        assert response.used_account_id == "account_2"
        assert response.data.reference_number == "REF12345"
        assert response.attempts == 2

        # Check key statuses
        metrics = await key_manager.get_all_metrics()
        acc1_metrics = next(m for m in metrics if m.account_id == "account_1")
        acc2_metrics = next(m for m in metrics if m.account_id == "account_2")

        assert acc1_metrics.status == "COOLDOWN"
        assert acc1_metrics.rate_limit_errors == 1
        assert acc2_metrics.status == "ACTIVE"
        assert acc2_metrics.successful_requests == 1
