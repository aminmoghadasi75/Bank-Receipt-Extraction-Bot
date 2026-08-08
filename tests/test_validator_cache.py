import pytest
from gateway.validator import ResponseValidator
from gateway.cache import ReceiptCacheManager


def test_json_repair_and_validation():
    # 1. Clean response wrapped in markdown block with trailing comma
    raw_response = """```json
    {
        "reference_number": "TRX-998877",
        "amount": 125000.0,
        "currency": "IRR",
        "sender_name": "Ali Ahmadi",
        "receiver_name": "Reza Rezaei",
        "bank_name": "Mellat",
        "transaction_status": "SUCCESS",
    }
    ```"""

    data, error = ResponseValidator.parse_and_validate(raw_response)
    assert error is None
    assert data is not None
    assert data.reference_number == "TRX-998877"
    assert data.amount == 125000.0
    assert data.sender_name == "Ali Ahmadi"


def test_cache_hit_and_miss():
    cache = ReceiptCacheManager(ttl_seconds=3600)
    image1 = b"sample_bank_receipt_bytes_1"
    image2 = b"sample_bank_receipt_bytes_2"

    hash1 = cache.compute_image_hash(image1)
    hash2 = cache.compute_image_hash(image2)

    assert cache.get(hash1) is None

    sample_ocr_dict = {
        "reference_number": "REF-CACHE-100",
        "amount": 75000.0,
        "bank_name": "Saman"
    }

    cache.set(hash1, sample_ocr_dict)

    # Check cache hit
    hit = cache.get(hash1)
    assert hit is not None
    assert hit["reference_number"] == "REF-CACHE-100"

    # Check miss on image 2
    assert cache.get(hash2) is None
