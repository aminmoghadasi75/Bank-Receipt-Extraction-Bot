"""
Receipt Formatter - formats extracted BankReceiptData into beautiful Persian-language
structured WhatsApp message text.
"""
from typing import Optional, Dict, Any


def _fmt_amount(value: Optional[float]) -> str:
    """Format amount with Persian comma-separated notation."""
    if value is None:
        return "نامشخص"
    try:
        int_val = int(value)
        formatted = f"{int_val:,}"
        return f"{formatted} ریال"
    except (ValueError, TypeError):
        return str(value)


def _or(value: Optional[str], fallback: str = "نامشخص") -> str:
    """Return value if truthy, else fallback."""
    if value and str(value).strip():
        return str(value).strip()
    return fallback


def _status_emoji(status: Optional[str]) -> str:
    """Map transaction status to emoji."""
    if not status:
        return "ℹ️"
    s = status.strip().lower()
    if any(k in s for k in ("موفق", "success", "successful")):
        return "✅"
    if any(k in s for k in ("ناموفق", "fail", "failed", "unsuccessful")):
        return "❌"
    return "ℹ️"


def _confidence_bar(score: float) -> str:
    """Simple 5-block confidence indicator."""
    filled = round(score * 5)
    bar = "🟩" * filled + "⬜" * (5 - filled)
    pct = int(score * 100)
    return f"{bar} {pct}%"


def format_receipt(data: Dict[str, Any]) -> str:
    """
    Format extracted receipt data dictionary into a beautiful Persian WhatsApp message.

    Args:
        data: Dictionary from BankReceiptData.model_dump()

    Returns:
        Formatted multi-line string ready to send via WhatsApp.
    """
    status = data.get("transaction_status")
    status_emoji = _status_emoji(status)
    status_text = _or(status, "نامشخص")
    amount = _fmt_amount(data.get("amount"))
    confidence = data.get("confidence_score", 0.0) or 0.0

    lines = [
        "🧾 *اطلاعات فیش بانکی*",
        "─────────────────────────",
        "",
    ]

    # Transaction info
    lines.append(f"{status_emoji} *وضعیت تراکنش:* {status_text}")
    lines.append(f"💰 *مبلغ:* {amount}")

    if data.get("transaction_datetime"):
        lines.append(f"📅 *تاریخ و ساعت:* {_or(data.get('transaction_datetime'))}")

    if data.get("title"):
        lines.append(f"📌 *عنوان:* {_or(data.get('title'))}")

    if data.get("transfer_type"):
        lines.append(f"🔄 *نوع انتقال:* {_or(data.get('transfer_type'))}")

    # Tracking IDs
    has_tracking = data.get("tracking_id") or data.get("transfer_tracking_number")
    if has_tracking:
        lines.append("")
        lines.append("🔢 *شناسه‌های پیگیری*")
        if data.get("tracking_id"):
            lines.append(f"  • شماره پیگیری: `{_or(data.get('tracking_id'))}`")
        if data.get("transfer_tracking_number"):
            lines.append(f"  • شماره مرجع/انتقال: `{_or(data.get('transfer_tracking_number'))}`")

    # Source (Payer) section
    has_source = any(
        data.get(k) for k in ["source_bank", "payer_name", "source_card", "source_account_number", "source_deposit_number"]
    )
    if has_source:
        lines.append("")
        lines.append("👤 *مبدا (پرداخت‌کننده)*")
        if data.get("payer_name"):
            lines.append(f"  • نام: {_or(data.get('payer_name'))}")
        if data.get("source_bank"):
            lines.append(f"  • بانک: {_or(data.get('source_bank'))}")
        if data.get("source_card"):
            card = _or(data.get("source_card"))
            if len(card) == 16 and card.isdigit():
                card = f"{card[:4]}-{card[4:8]}-{card[8:12]}-{card[12:]}"
            lines.append(f"  • کارت: `{card}`")
        if data.get("source_account_number"):
            lines.append(f"  • حساب: `{_or(data.get('source_account_number'))}`")
        if data.get("source_deposit_number"):
            lines.append(f"  • سپرده: `{_or(data.get('source_deposit_number'))}`")

    # Destination (Receiver) section
    has_dest = any(
        data.get(k) for k in ["destination_bank", "receiver_name", "destination_card",
                               "destination_account_number", "destination_iban"]
    )
    if has_dest:
        lines.append("")
        lines.append("🎯 *مقصد (دریافت‌کننده)*")
        if data.get("receiver_name"):
            lines.append(f"  • نام: {_or(data.get('receiver_name'))}")
        if data.get("destination_bank"):
            lines.append(f"  • بانک: {_or(data.get('destination_bank'))}")
        if data.get("destination_card"):
            card = _or(data.get("destination_card"))
            if len(card) == 16 and card.isdigit():
                card = f"{card[:4]}-{card[4:8]}-{card[8:12]}-{card[12:]}"
            lines.append(f"  • کارت: `{card}`")
        if data.get("destination_account_number"):
            lines.append(f"  • حساب: `{_or(data.get('destination_account_number'))}`")
        if data.get("destination_iban"):
            lines.append(f"  • شبا: `{_or(data.get('destination_iban'))}`")

    # Confidence
    lines.append("")
    lines.append("─────────────────────────")
    lines.append(f"📊 *دقت استخراج:* {_confidence_bar(confidence)}")
    lines.append("")
    lines.append("⚠️ *لطفاً اطلاعات را بررسی کرده و در صورت صحت، عبارت /تایید را ارسال کنید.*")

    return "\n".join(lines)


def format_receipt_confirmed(original_text: str) -> str:
    """
    Append confirmation stamp to the original extraction message.

    Args:
        original_text: The original formatted receipt text.

    Returns:
        Updated text with confirmation stamp appended.
    """
    prompt = "⚠️ *لطفاً اطلاعات را بررسی کرده و در صورت صحت، عبارت /تایید را ارسال کنید.*"
    text = original_text.replace(prompt, "").strip()
    return f"{text}\n\n✅ *تایید شده*"
