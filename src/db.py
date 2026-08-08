"""
Receipt Database Module - SQLite storage for receipt extraction records,
WhatsApp message mapping, and confirmation status.
"""
import json
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

# Database file path under project data/ directory
PROJECT_ROOT = Path(__file__).resolve().parent.parent
DB_DIR = PROJECT_ROOT / "data"
DB_PATH = DB_DIR / "receipts.db"


def get_connection(db_path: Optional[Path] = None) -> sqlite3.Connection:
    """Get a SQLite database connection, ensuring tables are initialized."""
    target_path = db_path or DB_PATH
    target_path.parent.mkdir(parents=True, exist_ok=True)
    
    conn = sqlite3.connect(str(target_path))
    conn.row_factory = sqlite3.Row
    return conn


def init_db(db_path: Optional[Path] = None) -> None:
    """Initialize the receipts SQLite database schema."""
    conn = get_connection(db_path)
    try:
        with conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS receipts (
                    id TEXT PRIMARY KEY,
                    whatsapp_message_id TEXT,
                    reply_message_id TEXT,
                    chat_id TEXT,
                    receipt_data TEXT NOT NULL,
                    formatted_text TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'PENDING',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
                """
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_reply_message_id ON receipts(reply_message_id);"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_chat_status ON receipts(chat_id, status);"
            )
    finally:
        conn.close()


def save_receipt(
    receipt_data: Dict[str, Any],
    formatted_text: str,
    whatsapp_message_id: Optional[str] = None,
    chat_id: Optional[str] = None,
    db_path: Optional[Path] = None,
) -> str:
    """
    Save a newly extracted receipt record with PENDING status.
    Returns the generated receipt UUID.
    """
    init_db(db_path)
    receipt_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()
    json_data = json.dumps(receipt_data, ensure_ascii=False)

    conn = get_connection(db_path)
    try:
        with conn:
            conn.execute(
                """
                INSERT INTO receipts (
                    id, whatsapp_message_id, reply_message_id, chat_id,
                    receipt_data, formatted_text, status, created_at, updated_at
                ) VALUES (?, ?, NULL, ?, ?, ?, 'PENDING', ?, ?)
                """,
                (
                    receipt_id,
                    whatsapp_message_id,
                    chat_id,
                    json_data,
                    formatted_text,
                    now,
                    now,
                ),
            )
        return receipt_id
    finally:
        conn.close()


def register_reply_message_id(
    receipt_id: str,
    reply_message_id: str,
    db_path: Optional[Path] = None,
) -> bool:
    """Bind the bot's sent WhatsApp reply message ID to the receipt record."""
    init_db(db_path)
    now = datetime.now(timezone.utc).isoformat()
    conn = get_connection(db_path)
    try:
        with conn:
            cursor = conn.execute(
                """
                UPDATE receipts
                SET reply_message_id = ?, updated_at = ?
                WHERE id = ?
                """,
                (reply_message_id, now, receipt_id),
            )
            return cursor.rowcount > 0
    finally:
        conn.close()


def confirm_receipt(
    receipt_id: Optional[str] = None,
    reply_message_id: Optional[str] = None,
    chat_id: Optional[str] = None,
    db_path: Optional[Path] = None,
) -> Optional[Dict[str, Any]]:
    """
    Mark a receipt as CONFIRMED.
    Searches by receipt_id, reply_message_id, or latest PENDING receipt in chat_id.
    """
    init_db(db_path)
    now = datetime.now(timezone.utc).isoformat()
    conn = get_connection(db_path)
    try:
        with conn:
            # 1. Search by receipt_id if provided
            if receipt_id:
                cursor = conn.execute("SELECT * FROM receipts WHERE id = ?", (receipt_id,))
                row = cursor.fetchone()
            # 2. Search by reply_message_id
            elif reply_message_id:
                cursor = conn.execute(
                    "SELECT * FROM receipts WHERE reply_message_id = ?", (reply_message_id,)
                )
                row = cursor.fetchone()
            # 3. Search for latest PENDING receipt in chat
            elif chat_id:
                cursor = conn.execute(
                    """
                    SELECT * FROM receipts
                    WHERE chat_id = ? AND status = 'PENDING'
                    ORDER BY created_at DESC LIMIT 1
                    """,
                    (chat_id,),
                )
                row = cursor.fetchone()
            else:
                return None

            if not row:
                return None

            target_id = row["id"]
            conn.execute(
                """
                UPDATE receipts
                SET status = 'CONFIRMED', updated_at = ?
                WHERE id = ?
                """,
                (now, target_id),
            )

            # Fetch updated row
            updated_row = conn.execute(
                "SELECT * FROM receipts WHERE id = ?", (target_id,)
            ).fetchone()
            
            res = dict(updated_row)
            res["receipt_data"] = json.loads(res["receipt_data"])
            return res
    finally:
        conn.close()


def get_pending_receipt(
    chat_id: Optional[str] = None,
    reply_message_id: Optional[str] = None,
    db_path: Optional[Path] = None,
) -> Optional[Dict[str, Any]]:
    """Get pending receipt record by reply_message_id or latest in chat."""
    init_db(db_path)
    conn = get_connection(db_path)
    try:
        if reply_message_id:
            cursor = conn.execute(
                "SELECT * FROM receipts WHERE reply_message_id = ? AND status = 'PENDING'",
                (reply_message_id,),
            )
        elif chat_id:
            cursor = conn.execute(
                """
                SELECT * FROM receipts
                WHERE chat_id = ? AND status = 'PENDING'
                ORDER BY created_at DESC LIMIT 1
                """,
                (chat_id,),
            )
        else:
            return None

        row = cursor.fetchone()
        if not row:
            return None

        res = dict(row)
        res["receipt_data"] = json.loads(res["receipt_data"])
        return res
    finally:
        conn.close()


def list_receipts(
    limit: int = 50,
    status: Optional[str] = None,
    db_path: Optional[Path] = None,
) -> List[Dict[str, Any]]:
    """List stored receipts sorted by creation time descending."""
    init_db(db_path)
    conn = get_connection(db_path)
    try:
        if status:
            cursor = conn.execute(
                "SELECT * FROM receipts WHERE status = ? ORDER BY created_at DESC LIMIT ?",
                (status, limit),
            )
        else:
            cursor = conn.execute(
                "SELECT * FROM receipts ORDER BY created_at DESC LIMIT ?", (limit,)
            )

        results = []
        for row in cursor.fetchall():
            item = dict(row)
            item["receipt_data"] = json.loads(item["receipt_data"])
            results.append(item)
        return results
    finally:
        conn.close()
