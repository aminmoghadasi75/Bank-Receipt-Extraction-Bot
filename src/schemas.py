import re
from typing import Optional
from pydantic import BaseModel, Field, field_validator


def normalize_digits(text: Optional[str]) -> Optional[str]:
    """Convert Persian/Arabic digits to ASCII digits."""
    if text is None:
        return None
    persian_arabic_map = {
        '۰': '0', '۱': '1', '۲': '2', '۳': '3', '۴': '4',
        '۵': '5', '۶': '6', '۷': '7', '۸': '8', '۹': '9',
        '٠': '0', '١': '1', '٢': '2', '٣': '3', '٤': '4',
        '٥': '5', '٦': '6', '٧': '7', '٨': '8', '٩': '9'
    }
    for fa_digit, en_digit in persian_arabic_map.items():
        text = text.replace(fa_digit, en_digit)
    return text


def clean_card_number(value: Optional[str]) -> Optional[str]:
    """Remove spaces/dashes from card number but preserve masking characters (* ٭).

    Banks like Bank Maskan display card numbers with masked middle digits,
    e.g. '6280 23*** **** 3406'. We keep these as-is after stripping spaces/dashes
    so the exact text from the receipt is preserved in the output.
    """
    if value is None or str(value).strip() == "":
        return None
    normalized = normalize_digits(str(value).strip())
    # Remove only spaces and dashes — keep digits AND masking chars (* ٭ ●)
    cleaned = re.sub(r"[\s\-]", "", normalized)
    return cleaned if cleaned else None


class ReceiptData(BaseModel):
    """Pydantic model representing structured Iranian bank receipt data."""

    # ── Transaction Info ──────────────────────────────────────────────────────
    amount: Optional[int] = Field(default=None, description="Transaction amount in Rials/Tomans")
    title: Optional[str] = Field(default=None, description="Receipt title / transaction description")
    transaction_status: Optional[str] = Field(default=None, description="Transaction status (موفق / ناموفق)")
    transaction_datetime: Optional[str] = Field(default=None, description="Transaction date and time combined")
    tracking_id: Optional[str] = Field(default=None, description="شناسه پیگیری (unique tracking identifier)")
    transfer_tracking_number: Optional[str] = Field(default=None, description="شماره پیگیری انتقال وجه")
    transfer_type: Optional[str] = Field(default=None, description="Transfer type: پایا / ساتنا / پل / کارت‌به‌کارت / ...")

    # ── Source (Payer) ────────────────────────────────────────────────────────
    source_bank: Optional[str] = Field(default=None, description="Source bank name")
    source_deposit_number: Optional[str] = Field(default=None, description="Source deposit / account number")
    source_account_number: Optional[str] = Field(default=None, description="Source bank account number")
    source_card: Optional[str] = Field(default=None, description="Source 16-digit card number")
    payer_name: Optional[str] = Field(default=None, description="Payer / source account owner full name")

    # ── Destination (Receiver) ────────────────────────────────────────────────
    destination_bank: Optional[str] = Field(default=None, description="Destination bank name")
    destination_iban: Optional[str] = Field(default=None, description="Destination IBAN / شبا")
    destination_account_number: Optional[str] = Field(default=None, description="Destination bank account number")
    destination_card: Optional[str] = Field(default=None, description="Destination 16-digit card number")
    receiver_name: Optional[str] = Field(default=None, description="Receiver / destination account owner full name")

    # ── Internal Metadata (not exported to Excel) ─────────────────────────────
    confidence_score: float = Field(default=0.0, description="Internal OCR/LLM confidence score")
    requires_manual_review: bool = Field(
        default=False,
        description="Flag indicating if receipt needs human inspection"
    )

    @field_validator("source_card", "destination_card", mode="before")
    @classmethod
    def validate_card_number(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return None
        cleaned = clean_card_number(v)
        if cleaned is None:
            return None

        # If value looks like an IBAN (starts with IR), silently discard it.
        # IBANs belong in destination_iban — they must NOT be stored as card numbers.
        if cleaned.upper().startswith("IR"):
            return None

        # Only enforce strict 16-digit rule when the number is fully revealed.
        # If the card has masking chars (* ٭ ●), accept it as extracted from the receipt.
        digits_only = re.sub(r"[^\d]", "", cleaned)
        has_masking = bool(re.search(r"[*٭●]", cleaned))
        if not has_masking and len(digits_only) != 16:
            # Incomplete card number — do not raise, just discard to avoid blocking the record
            return None
        return cleaned

    @field_validator("amount", mode="before")
    @classmethod
    def validate_amount(cls, v: Optional[object]) -> Optional[int]:
        if v is None or v == "":
            return None
        if isinstance(v, (int, float)):
            val = int(v)
        elif isinstance(v, str):
            normalized = normalize_digits(v)
            cleaned = re.sub(r"\D", "", normalized)
            if not cleaned:
                return None
            val = int(cleaned)
        else:
            raise ValueError(f"Invalid amount type: {type(v)}")

        if val <= 0:
            raise ValueError(f"Amount must be greater than 0, got {val}")
        return val

    @field_validator(
        "transaction_datetime", "tracking_id", "transfer_tracking_number",
        "source_deposit_number", "source_account_number", "destination_account_number",
        "destination_iban", "title", "transfer_type",
        mode="before"
    )
    @classmethod
    def normalize_string_fields(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return None
        return normalize_digits(str(v).strip())


# Alias for backward compatibility across modules
BankReceiptData = ReceiptData

