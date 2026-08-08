import re
import json
import logging
from typing import Optional, Tuple, Dict, Any
from pydantic import ValidationError
from gateway.models import BankReceiptData

logger = logging.getLogger("gemini_gateway.validator")

SYSTEM_OCR_PROMPT = """You are an expert AI OCR engine specialized in extracting structured data from **Iranian bank receipt images** (فیش‌های بانکی ایرانی).

Your ONLY output must be a single valid JSON object — no markdown, no explanation, no extra text.

## Target JSON Schema

```json
{
  "amount": <integer or float — transaction amount in Rials/Tomans, numbers only, no commas>,
  "title": "<string — receipt title or transaction description (عنوان تراکنش) or null>",
  "transaction_status": "<string — موفق / ناموفق / SUCCESS / FAILED / PENDING or null>",
  "transaction_datetime": "<string — full date and time as shown on receipt, e.g. '1403/05/16 14:32:00' or null>",
  "tracking_id": "<string — شناسه پیگیری, the main unique receipt tracking code printed on the receipt or null>",
  "transfer_tracking_number": "<string — شماره پیگیری انتقال وجه, separate from tracking_id, often labeled 'شماره پیگیری' or null>",
  "transfer_type": "<string — نوع انتقال: پایا / ساتنا / پل / کارت‌به‌کارت / ACH / RTGS or null>",
  "source_bank": "<string — name of the SOURCE (sender/payer) bank in Persian e.g. 'بانک رفاه کارگران' or null>",
  "source_deposit_number": "<string — شماره سپرده مبدا (deposit account number of sender) or null>",
  "source_account_number": "<string — شماره حساب مبدا (bank account number of sender) or null>",
  "source_card": "<string — 16-digit card number of SENDER, digits only no dashes, e.g. '6037991234567890' or null>",
  "payer_name": "<string — full name of the PAYER / sender (نام صاحب حساب / سپرده مبدا) or null>",
  "destination_bank": "<string — name of the DESTINATION (receiver) bank in Persian or null>",
  "destination_iban": "<string — IBAN / شبا of destination, always starts with 'IR' followed by 24 digits, e.g. 'IR580690060482400835486001' or null>",
  "destination_account_number": "<string — شماره حساب مقصد (bank account number of receiver) or null>",
  "destination_card": "<string — 16-digit card number of RECEIVER, digits only no dashes or null>",
  "receiver_name": "<string — full name of the RECEIVER / destination account owner (نام صاحب شبا / حساب مقصد) or null>",
  "confidence_score": <float between 0.0 and 1.0 — your confidence in the overall extraction quality>
}
```

## Critical Rules

1. **IBAN vs Card Number**: An IBAN (شبا) always starts with "IR" and has 26 characters total. A card number is exactly 16 digits. NEVER put an IBAN value in `source_card` or `destination_card`. Put IBANs only in `destination_iban`.

2. **Card Numbers**: Extract all 16 digits. Remove spaces and dashes. If digits are partially masked (e.g. '6037-99**-****-1234'), include the masked form with asterisks. If fewer than 16 digits are visible and no masking is present, set to null — do NOT guess.

3. **Amount**: Extract as a plain number (integer or float). Remove all commas, spaces, and currency labels. Example: '۴۰۰,۰۰۰,۰۰۰ ریال' → 400000000.

4. **tracking_id vs transfer_tracking_number**: These are two different fields:
   - `tracking_id` = شناسه پیگیری (unique receipt ID, usually long numeric string like '140504090132049236')
   - `transfer_tracking_number` = شماره پیگیری انتقال وجه (shorter reference for the transfer itself)

5. **Persian/Arabic digits**: Convert all Persian/Arabic-Indic digits (۰-۹ / ٠-٩) to ASCII digits (0-9) in every field.

6. **Null vs empty string**: Use JSON null (not empty string "") for any field not visible on the receipt.

7. **transaction_status**: Use the exact Persian text from the receipt if available (e.g. 'موفق'), otherwise map SUCCESS/FAILED/PENDING.

8. **source_bank**: Extract the bank name of the SENDER side. This is usually shown at the top or labeled as 'بانک مبدا' or part of the receipt header.

Output ONLY the JSON object. No explanation.
"""

RETRY_REPAIR_PROMPT = """The previous JSON output was invalid or incomplete. Re-examine the receipt image carefully and return a strictly valid JSON object.

Required schema (use null for any field not found):
{
  "amount": <number>,
  "title": "<string or null>",
  "transaction_status": "<string or null>",
  "transaction_datetime": "<string or null>",
  "tracking_id": "<string or null>",
  "transfer_tracking_number": "<string or null>",
  "transfer_type": "<string or null>",
  "source_bank": "<string or null>",
  "source_deposit_number": "<string or null>",
  "source_account_number": "<string or null>",
  "source_card": "<16-digit string or null — NEVER put IBAN here>",
  "payer_name": "<string or null>",
  "destination_bank": "<string or null>",
  "destination_iban": "<IR + 24 digits or null>",
  "destination_account_number": "<string or null>",
  "destination_card": "<16-digit string or null — NEVER put IBAN here>",
  "receiver_name": "<string or null>",
  "confidence_score": <float 0.0-1.0>
}

Rules: IBAN starts with IR (goes in destination_iban). Card numbers are exactly 16 digits (goes in source_card or destination_card). Output ONLY valid JSON.
"""


class ResponseValidator:
    """Validates and repairs JSON responses returned by Gemini Vision API."""

    @staticmethod
    def clean_json_string(raw_text: str) -> str:
        """Strip markdown syntax blocks and whitespace."""
        text = raw_text.strip()
        # Remove ```json ... ``` or ``` ... ``` wrappers
        text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.IGNORECASE)
        text = re.sub(r"\s*```$", "", text)
        return text.strip()

    @classmethod
    def attempt_json_repair(cls, raw_text: str) -> Optional[Dict[str, Any]]:
        """Attempt to repair common JSON formatting defects from LLM outputs."""
        cleaned = cls.clean_json_string(raw_text)
        
        # Attempt 1: Standard json parse
        try:
            return json.loads(cleaned)
        except json.JSONDecodeError:
            pass

        # Attempt 2: Extract first {...} block with regex
        match = re.search(r"\{.*\}", cleaned, re.DOTALL)
        if match:
            extracted = match.group(0)
            try:
                return json.loads(extracted)
            except json.JSONDecodeError:
                pass
            
            # Fix trailing commas: {"key": "val", } -> {"key": "val"}
            fixed_commas = re.sub(r",\s*([\}\]])", r"\1", extracted)
            try:
                return json.loads(fixed_commas)
            except json.JSONDecodeError:
                pass

        return None

    @classmethod
    def parse_and_validate(cls, raw_response_text: str) -> Tuple[Optional[BankReceiptData], Optional[str]]:
        """Parses raw Gemini text output into BankReceiptData.
        
        Returns:
            (BankReceiptData instance, error_message)
        """
        parsed_dict = cls.attempt_json_repair(raw_response_text)
        if parsed_dict is None:
            return None, "Failed to parse valid JSON from model response."

        try:
            # Validate with Pydantic
            receipt = BankReceiptData(**parsed_dict)
            return receipt, None
        except ValidationError as ve:
            logger.warning(f"Pydantic validation error on parsed JSON: {ve}")
            return None, f"Schema validation error: {str(ve)}"
