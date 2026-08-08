from src.validator import ReceiptValidator


def test_validator_valid_data():
    validator = ReceiptValidator()
    raw = {
        "bank_name": "سامان",
        "amount": "500000",
        "tracking_number": "123456",
        "date": "1402/10/10"
    }
    receipt = validator.validate(raw)
    assert receipt.bank_name == "سامان"
    assert receipt.amount == 500000
    assert receipt.requires_manual_review is False
    assert receipt.confidence_score > 0.5


def test_validator_invalid_card_flagged():
    validator = ReceiptValidator()
    raw = {
        "bank_name": "ملت",
        "source_card": "invalid_card",
        "amount": "1000",
        "tracking_number": "9999"
    }
    receipt = validator.validate(raw)
    assert receipt.requires_manual_review is True
