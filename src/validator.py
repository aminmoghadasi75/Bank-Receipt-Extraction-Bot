from typing import Dict, Any
from loguru import logger
from pydantic import ValidationError

from src.schemas import ReceiptData


class ReceiptValidator:
    """Validates raw dictionary output from LLM against ReceiptData schema and business rules."""

    @staticmethod
    def remap_aliases(raw_data: Dict[str, Any]) -> Dict[str, Any]:
        """Remap common JSON key aliases to ReceiptData schema field names.

        Covers both old gateway field names (pre-alignment) and any alternative
        labels that Gemini might produce despite prompt instructions.
        """
        mapped = dict(raw_data)

        alias_map = {
            # Old gateway field names → ReceiptData field names
            "bank_name":              "source_bank",
            "reference_number":       "tracking_id",
            "tracking_number":        "tracking_id",
            "date":                   "transaction_datetime",
            "transaction_date":       "transaction_datetime",
            "sender_name":            "payer_name",
            # Guard: only map sender_account to source_card if it looks like a card number
            # (handled below in logic, alias here is for plain text labels)
            # Notes field — map to title if title is missing
            "notes":                  "title",
        }

        for alias, target in alias_map.items():
            if alias in mapped and mapped[alias] is not None:
                if target not in mapped or mapped[target] is None:
                    mapped[target] = mapped[alias]

        # Special case: sender_account — could be a card number or account number
        # Route it to source_card only if it looks like a 16-digit number;
        # otherwise route to source_account_number
        if "sender_account" in mapped and mapped["sender_account"] is not None:
            val = str(mapped["sender_account"]).replace("-", "").replace(" ", "")
            digits_only = "".join(c for c in val if c.isdigit())
            if len(digits_only) == 16:
                if not mapped.get("source_card"):
                    mapped["source_card"] = mapped["sender_account"]
            else:
                if not mapped.get("source_account_number"):
                    mapped["source_account_number"] = mapped["sender_account"]

        # Special case: receiver_account — same logic as sender_account but for destination
        if "receiver_account" in mapped and mapped["receiver_account"] is not None:
            val = str(mapped["receiver_account"]).replace("-", "").replace(" ", "")
            # If IBAN (starts with IR or ir), put in destination_iban
            if val.upper().startswith("IR"):
                if not mapped.get("destination_iban"):
                    mapped["destination_iban"] = mapped["receiver_account"]
            else:
                digits_only = "".join(c for c in val if c.isdigit())
                if len(digits_only) == 16:
                    if not mapped.get("destination_card"):
                        mapped["destination_card"] = mapped["receiver_account"]
                else:
                    if not mapped.get("destination_account_number"):
                        mapped["destination_account_number"] = mapped["receiver_account"]

        return mapped


    @staticmethod
    def calculate_confidence_score(data: ReceiptData) -> float:
        """Calculate a heuristic confidence score (0.0 to 1.0) based on critical fields presence."""
        score = 0.0
        weights = {
            "amount":                   0.20,
            "tracking_id":              0.15,
            "transfer_tracking_number": 0.10,
            "transaction_datetime":     0.10,
            "transaction_status":       0.10,
            "source_bank":              0.08,
            "destination_bank":         0.07,
            "destination_iban":         0.07,
            "destination_card":         0.05,
            "source_card":              0.04,
            "receiver_name":            0.02,
            "payer_name":               0.02,
        }

        for field, weight in weights.items():
            val = getattr(data, field, None)
            if val is not None and str(val).strip() != "":
                score += weight

        return round(score, 2)

    def validate(self, raw_data: Dict[str, Any]) -> ReceiptData:
        """Validate raw dictionary data into ReceiptData."""
        data_to_validate = self.remap_aliases(raw_data)

        try:
            receipt = ReceiptData(**data_to_validate)
            receipt.confidence_score = self.calculate_confidence_score(receipt)

            # Check business logic triggers for manual review
            if not receipt.amount or not (receipt.tracking_id or receipt.transfer_tracking_number):
                logger.warning(
                    f"Critical fields missing (amount={receipt.amount}, "
                    f"tracking_id={receipt.tracking_id}, "
                    f"transfer_tracking_number={receipt.transfer_tracking_number}). "
                    "Flagging for manual review."
                )
                receipt.requires_manual_review = True

            if receipt.confidence_score < 0.5:
                logger.warning(f"Low confidence score ({receipt.confidence_score}). Flagging for manual review.")
                receipt.requires_manual_review = True

            logger.info(
                f"Validation successful. tracking_id='{receipt.tracking_id}', "
                f"Amount={receipt.amount}, Confidence={receipt.confidence_score}"
            )
            return receipt

        except ValidationError as ve:
            logger.error(f"Pydantic Validation Error: {ve}")

            # Construct fallback object with manual review flag
            valid_fields: Dict[str, Any] = {}
            for field in ReceiptData.model_fields.keys():
                if field in data_to_validate and data_to_validate[field] is not None:
                    try:
                        temp = ReceiptData(**{field: data_to_validate[field]})
                        valid_fields[field] = getattr(temp, field)
                    except ValidationError:
                        pass

            valid_fields["requires_manual_review"] = True
            fallback_receipt = ReceiptData(**valid_fields)
            fallback_receipt.confidence_score = self.calculate_confidence_score(fallback_receipt)
            return fallback_receipt

        except Exception as e:
            logger.error(f"Unexpected error during validation: {e}")
            return ReceiptData(requires_manual_review=True, confidence_score=0.0)
