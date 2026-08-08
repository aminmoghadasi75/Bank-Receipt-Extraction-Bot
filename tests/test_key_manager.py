import time
import pytest
from gateway.key_manager import APIKeyManager, KeyState
from gateway.models import KeyStatus


@pytest.mark.asyncio
async def test_key_manager_initialization():
    raw_keys = ["KEY_A_12345678", "KEY_B_87654321", "KEY_C_11223344"]
    manager = APIKeyManager(raw_api_keys=raw_keys)
    
    metrics = await manager.get_all_metrics()
    assert len(metrics) == 3
    assert metrics[0].account_id == "account_1"
    assert metrics[0].status == KeyStatus.ACTIVE
    assert metrics[0].api_key_masked == "KEY_...5678"


@pytest.mark.asyncio
async def test_key_rotation_and_scoring():
    raw_keys = ["KEY_A_12345678", "KEY_B_87654321"]
    manager = APIKeyManager(raw_api_keys=raw_keys)

    # First pick should get account_1 or account_2
    key1 = await manager.get_best_key()
    assert key1 is not None
    await manager.record_success(key1.account_id, latency_seconds=0.5)

    # Second pick should favor key used less recently (even load distribution)
    key2 = await manager.get_best_key()
    assert key2 is not None
    assert key2.account_id != key1.account_id


@pytest.mark.asyncio
async def test_rate_limit_cooldown_and_backoff():
    raw_keys = ["KEY_1_00000000"]
    manager = APIKeyManager(raw_api_keys=raw_keys)

    # Trigger 1st 429 error
    await manager.record_rate_limit("account_1")
    metrics = (await manager.get_all_metrics())[0]
    
    assert metrics.status == KeyStatus.COOLDOWN
    assert metrics.cooldown_until is not None
    assert metrics.consecutive_429_count == 1

    # Should not return key while in cooldown
    key = await manager.get_best_key()
    assert key is None


@pytest.mark.asyncio
async def test_auth_error_disables_key():
    raw_keys = ["KEY_AUTH_ERR_1234"]
    manager = APIKeyManager(raw_api_keys=raw_keys)

    await manager.record_auth_error("account_1", status_code=401)
    metrics = (await manager.get_all_metrics())[0]

    assert metrics.status == KeyStatus.DISABLED
    key = await manager.get_best_key()
    assert key is None


@pytest.mark.asyncio
async def test_manual_key_reset():
    raw_keys = ["KEY_RESET_1234"]
    manager = APIKeyManager(raw_api_keys=raw_keys)

    await manager.record_auth_error("account_1", status_code=403)
    assert (await manager.get_all_metrics())[0].status == KeyStatus.DISABLED

    res = await manager.reset_key_status("account_1")
    assert res is True
    assert (await manager.get_all_metrics())[0].status == KeyStatus.ACTIVE
