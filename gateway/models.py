from enum import Enum
from datetime import datetime
from typing import Optional, List, Any, Dict
from pydantic import BaseModel, Field


class KeyStatus(str, Enum):
    ACTIVE = "ACTIVE"
    RATE_LIMITED = "RATE_LIMITED"
    COOLDOWN = "COOLDOWN"
    FAILED = "FAILED"
    DISABLED = "DISABLED"


class APIKeyMetrics(BaseModel):
    account_id: str
    api_key_masked: str
    status: KeyStatus = KeyStatus.ACTIVE
    total_requests: int = 0
    successful_requests: int = 0
    failed_requests: int = 0
    rate_limit_errors: int = 0
    last_used_time: Optional[float] = None
    last_error_time: Optional[float] = None
    cooldown_until: Optional[float] = None
    average_response_time: float = 0.0
    consecutive_429_count: int = 0
    score: float = 100.0


class BankReceiptData(BaseModel):
    """Structured Pydantic model for Iranian Bank Receipt OCR data.

    Field names are intentionally aligned with ReceiptData (src/schemas.py)
    so that gateway output maps directly to the Excel export schema without
    any lossy alias translation.
    """

    # ── Transaction Info ──────────────────────────────────────────────────────
    amount: Optional[float] = Field(default=None, description="Transaction amount (Rials or Tomans)")
    title: Optional[str] = Field(default=None, description="Receipt title or transaction description (عنوان تراکنش)")
    transaction_status: Optional[str] = Field(default=None, description="موفق / ناموفق / SUCCESS / FAILED")
    transaction_datetime: Optional[str] = Field(default=None, description="Combined date+time string e.g. '1403/05/16 14:32:00'")
    tracking_id: Optional[str] = Field(default=None, description="شناسه پیگیری — unique tracking identifier printed on receipt")
    transfer_tracking_number: Optional[str] = Field(default=None, description="شماره پیگیری انتقال وجه (separate from tracking_id)")
    transfer_type: Optional[str] = Field(default=None, description="نوع انتقال: پایا / ساتنا / پل / کارت‌به‌کارت / ACH / RTGS")

    # ── Source (Payer) ────────────────────────────────────────────────────────
    source_bank: Optional[str] = Field(default=None, description="Name of source / payer bank (بانک مبدا)")
    source_deposit_number: Optional[str] = Field(default=None, description="Source deposit or savings account number (شماره سپرده مبدا)")
    source_account_number: Optional[str] = Field(default=None, description="Source bank account number (شماره حساب مبدا)")
    source_card: Optional[str] = Field(default=None, description="Source 16-digit card number (شماره کارت مبدا) — digits only, no dashes")
    payer_name: Optional[str] = Field(default=None, description="Full name of payer / source account owner (نام صاحب حساب مبدا)")

    # ── Destination (Receiver) ────────────────────────────────────────────────
    destination_bank: Optional[str] = Field(default=None, description="Name of destination / receiver bank (بانک مقصد)")
    destination_iban: Optional[str] = Field(default=None, description="Destination IBAN / شبا — starts with IR, 26 chars")
    destination_account_number: Optional[str] = Field(default=None, description="Destination bank account number (شماره حساب مقصد)")
    destination_card: Optional[str] = Field(default=None, description="Destination 16-digit card number (شماره کارت مقصد) — digits only, no dashes")
    receiver_name: Optional[str] = Field(default=None, description="Full name of receiver / destination account owner (نام صاحب شبا مقصد)")

    # ── Internal ──────────────────────────────────────────────────────────────
    confidence_score: float = Field(default=1.0, description="Extraction confidence score from 0.0 to 1.0")


class OCRResponse(BaseModel):
    success: bool
    data: Optional[BankReceiptData] = None
    error: Optional[str] = None
    cached: bool = False
    used_account_id: Optional[str] = None
    attempts: int = 1
    latency_seconds: float = 0.0
