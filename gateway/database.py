import os
import time
import json
import sqlite3
import logging
from typing import List, Dict, Any, Optional

logger = logging.getLogger("gemini_gateway.database")

DB_FILE = "gateway.db"

class GatewayDatabase:
    """SQLite Database implementation for storing request logs and receipt OCR records."""

    def __init__(self, db_path: str = DB_FILE):
        self.db_path = db_path
        self._init_tables()

    def _get_connection(self):
        return sqlite3.connect(self.db_path)

    def _init_tables(self):
        """Initialize database schema."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            
            # OCR Requests Log table
            cursor.execute("""
            CREATE TABLE IF NOT EXISTS ocr_records (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                image_hash TEXT NOT NULL,
                used_account_id TEXT,
                reference_number TEXT,
                amount REAL,
                currency TEXT,
                sender_name TEXT,
                receiver_name TEXT,
                bank_name TEXT,
                status TEXT,
                success INTEGER,
                cached INTEGER,
                attempts INTEGER,
                latency_seconds REAL,
                raw_json TEXT,
                created_at REAL
            );
            """)

            # Key status & audit logs table
            cursor.execute("""
            CREATE TABLE IF NOT EXISTS key_audit_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                account_id TEXT NOT NULL,
                event_type TEXT NOT NULL,
                details TEXT,
                created_at REAL
            );
            """)

            conn.commit()
            logger.info("Database tables initialized successfully.")

    async def save_ocr_record(
        self,
        image_hash: str,
        used_account_id: Optional[str],
        success: bool,
        cached: bool,
        attempts: int,
        latency_seconds: float,
        ocr_data: Optional[Dict[str, Any]] = None,
        error_msg: Optional[str] = None
    ):
        """Asynchronously log OCR execution record."""
        now = time.time()
        ref = ocr_data.get("reference_number") if ocr_data else None
        amt = ocr_data.get("amount") if ocr_data else None
        curr = ocr_data.get("currency") if ocr_data else None
        s_name = ocr_data.get("sender_name") if ocr_data else None
        r_name = ocr_data.get("receiver_name") if ocr_data else None
        b_name = ocr_data.get("bank_name") if ocr_data else None
        status = ocr_data.get("transaction_status", "SUCCESS") if ocr_data else "FAILED"
        raw_json_str = json.dumps(ocr_data) if ocr_data else json.dumps({"error": error_msg})

        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO ocr_records (
                    image_hash, used_account_id, reference_number, amount, currency,
                    sender_name, receiver_name, bank_name, status, success, cached,
                    attempts, latency_seconds, raw_json, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                image_hash, used_account_id, ref, amt, curr,
                s_name, r_name, b_name, status, 1 if success else 0, 1 if cached else 0,
                attempts, latency_seconds, raw_json_str, now
            ))
            conn.commit()

    async def log_key_event(self, account_id: str, event_type: str, details: str):
        """Log key state transition event."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO key_audit_logs (account_id, event_type, details, created_at)
                VALUES (?, ?, ?, ?)
            """, (account_id, event_type, details, time.time()))
            conn.commit()

    async def get_recent_ocr_records(self, limit: int = 50) -> List[Dict[str, Any]]:
        """Retrieve recent OCR extraction history."""
        with self._get_connection() as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM ocr_records ORDER BY id DESC LIMIT ?", (limit,))
            rows = cursor.fetchall()
            return [dict(r) for r in rows]
