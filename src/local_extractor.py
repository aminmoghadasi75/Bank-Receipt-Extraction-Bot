import re
from typing import Dict, Any, Optional, List
from loguru import logger
from src.schemas import normalize_digits

class LocalRegexExtractor:
    """Local fallback rule-based extractor using regex patterns for Iranian bank receipts."""

    BANKS = [
        "ملی", "ملت", "صادرات", "تجارت", "سپه", "کشاورزی", "مسکن", "سامان",
        "پاسارگاد", "پارسیان", "اقتصاد نوین", "کارآفرین", "سینا", "شهر", "دی",
        "انصار", "مهر ایران", "رسالت", "بلو", "پست بانک", "خاورمیانه", "گردشگری"
    ]

    def extract_structured_data(self, ocr_text: str) -> Dict[str, Any]:
        if not ocr_text or not ocr_text.strip():
            return {}

        normalized_text = normalize_digits(ocr_text)
        lines = [line.strip() for line in normalized_text.split('\n') if line.strip()]

        result: Dict[str, Any] = {
            "bank_name": None,
            "payer_name": None,
            "receiver_name": None,
            "source_card": None,
            "destination_card": None,
            "amount": None,
            "date": None,
            "time": None,
            "tracking_number": None,
            "status": "موفق" if any(s in normalized_text for s in ["موفق", "موفقیت", "انجام شد", "تایید"]) else None
        }

        # 1. Extract Bank Name
        for bank in self.BANKS:
            if bank in normalized_text:
                result["bank_name"] = bank
                break

        # 2. Extract 16-digit Card Numbers
        cards = re.findall(r'\b(?:\d[ -\u200c]?){16}\b|\b\d{16}\b|\b\d{4}[ -]?\d{4}[ -]?\d{4}[ -]?\d{4}\b', normalized_text)
        cleaned_cards = [re.sub(r'\D', '', c) for c in cards if len(re.sub(r'\D', '', c)) == 16]
        # Remove duplicates while preserving order
        unique_cards = list(dict.fromkeys(cleaned_cards))
        if len(unique_cards) >= 1:
            result["destination_card"] = unique_cards[0]
        if len(unique_cards) >= 2:
            result["source_card"] = unique_cards[1]

        # Masked card fallback (e.g. 603799****1234 or 6037****1234)
        if not result["destination_card"]:
            masked_cards = re.findall(r'\b\d{4,6}[*xX\u200c -]+\d{4}\b', normalized_text)
            if masked_cards:
                result["destination_card"] = masked_cards[0]

        # 3. Extract Amount (Looking for keywords like مبلغ or numerical values with ریال / تومان / commas)
        amount_patterns = [
            r'(?:مبلغ|مبلغ کل|مبلغ واریزی|مبلغ انتقال)[:\s]*([\d,]+)',
            r'([\d,]{4,15})\s*(?:ریال|تومان)',
            r'\b(\d{1,3}(?:,\d{3})+)\b'
        ]
        for pattern in amount_patterns:
            matches = re.findall(pattern, normalized_text)
            if matches:
                clean_num = re.sub(r'\D', '', matches[0])
                if clean_num and len(clean_num) >= 4:
                    result["amount"] = int(clean_num)
                    break

        # 4. Extract Date (Solar Hijri format: 140x/xx/xx or 140x-xx-xx)
        date_match = re.search(r'\b(140[0-9][/.-]\d{1,2}[/.-]\d{1,2})\b', normalized_text)
        if date_match:
            result["date"] = date_match.group(1)

        # 5. Extract Time (HH:MM:SS or HH:MM)
        time_match = re.search(r'\b([012]?\d:[05]\d(?::[05]\d)?)\b', normalized_text)
        if time_match:
            result["time"] = time_match.group(1)

        # 6. Extract Tracking Number (شماره پیگیری / شماره ارجاع / مرجع)
        tracking_patterns = [
            r'(?:شماره پیگیری|شماره ارجاع|کد پیگیری|شماره مرجع|پیگیری|ارجاع)[:\s]*([0-9]{4,20})',
            r'\b([0-9]{6,14})\b'
        ]
        for pattern in tracking_patterns:
            matches = re.findall(pattern, normalized_text)
            if matches:
                # Exclude if it matched a card digit or date segment
                for m in matches:
                    if len(m) != 16 and not m.startswith("140"):
                        result["tracking_number"] = m
                        break
                if result["tracking_number"]:
                    break

        # 7. Names (Payer / Receiver)
        for line in lines:
            if "به نام" in line or "گیرنده" in line or "مقصد" in line:
                name = re.sub(r'.*(?:به نام|گیرنده|مقصد)[:\s]*', '', line).strip()
                if name and not any(char.isdigit() for char in name):
                    result["receiver_name"] = name
            elif "از طرف" in line or "فرستنده" in line or "مبدا" in line:
                name = re.sub(r'.*(?:از طرف|فرستنده|مبدا)[:\s]*', '', line).strip()
                if name and not any(char.isdigit() for char in name):
                    result["payer_name"] = name

        return result
