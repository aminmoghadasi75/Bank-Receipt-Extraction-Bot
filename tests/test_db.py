"""
Unit tests for SQLite database receipt storage operations.
"""
import tempfile
from pathlib import Path
from src.db import (
    init_db,
    save_receipt,
    register_reply_message_id,
    confirm_receipt,
    get_pending_receipt,
    list_receipts,
)


def test_db_workflow():
    with tempfile.TemporaryDirectory() as tmp_dir:
        db_path = Path(tmp_dir) / "test_receipts.db"

        init_db(db_path)

        receipt_data = {
            "amount": 500000.0,
            "tracking_id": "99887766",
            "source_bank": "ملی",
            "destination_bank": "سامان",
            "transaction_status": "موفق",
        }
        formatted_text = "اطلاعات فیش بانکی استخراج شد."
        whatsapp_msg_id = "wamid.HBgLMzEwNDY"
        chat_id = "989123456789@c.us"

        # 1. Save receipt
        receipt_id = save_receipt(
            receipt_data=receipt_data,
            formatted_text=formatted_text,
            whatsapp_message_id=whatsapp_msg_id,
            chat_id=chat_id,
            db_path=db_path,
        )
        assert receipt_id is not None

        # 2. Check pending
        pending = get_pending_receipt(chat_id=chat_id, db_path=db_path)
        assert pending is not None
        assert pending["id"] == receipt_id
        assert pending["status"] == "PENDING"
        assert pending["receipt_data"]["tracking_id"] == "99887766"

        # 3. Register reply message ID
        reply_msg_id = "wamid.BOT_REPLY_123"
        ok = register_reply_message_id(receipt_id, reply_msg_id, db_path=db_path)
        assert ok is True

        # 4. Confirm receipt by reply_msg_id
        confirmed = confirm_receipt(reply_message_id=reply_msg_id, db_path=db_path)
        assert confirmed is not None
        assert confirmed["status"] == "CONFIRMED"
        assert confirmed["id"] == receipt_id

        # 5. List receipts
        all_items = list_receipts(db_path=db_path)
        assert len(all_items) == 1
        assert all_items[0]["status"] == "CONFIRMED"
