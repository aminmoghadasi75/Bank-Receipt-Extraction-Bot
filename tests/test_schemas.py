import pytest
from pydantic import ValidationError
from src.schemas import ReceiptData, normalize_digits, clean_card_number


def test_normalize_digits():
    fa_digits = "۱۲۳۴۵۶۷۸۹۰"
    assert normalize_digits(fa_digits) == "1234567890"
    ar_digits = "١٢٣٤٥٦٧٨٩٠"
    assert normalize_digits(ar_digits) == "1234567890"
    assert normalize_digits(None) is None


def test_clean_card_number():
    raw_card = "6037-9918-1234-5678"
    assert clean_card_number(raw_card) == "6037991812345678"
    fa_card = "۶۰۳۷ ۹۹۱۸ ۱۲۳۴ ۵۶۷۸"
    assert clean_card_number(fa_card) == "6037991812345678"


def test_receipt_data_valid():
    data = {
        "bank_name": "ملی",
        "payer_name": "علی محمدی",
        "receiver_name": "رضا حسینی",
        "source_card": "6037991812345678",
        "destination_card": "6104337890123456",
        "amount": "100,000",
        "date": "1402/11/05",
        "time": "14:30",
        "tracking_number": "987654321",
        "status": "موفق"
    }
    receipt = ReceiptData(**data)
    assert receipt.bank_name == "ملی"
    assert receipt.source_card == "6037991812345678"
    assert receipt.amount == 100000
    assert receipt.requires_manual_review is False


def test_receipt_data_invalid_card():
    data = {
        "source_card": "123"  # Invalid 3 digits card
    }
    with pytest.raises(ValidationError):
        ReceiptData(**data)


def test_receipt_data_invalid_amount():
    data = {
        "amount": -500
    }
    with pytest.raises(ValidationError):
        ReceiptData(**data)
