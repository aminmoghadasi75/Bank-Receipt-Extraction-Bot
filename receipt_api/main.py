"""
Receipt API - FastAPI HTTP server bridging the WhatsApp Bot
to the Python Gemini Gateway and SQLite Database storage.

Endpoints:
  POST /extract-receipt      - Accept base64 image, run Gemini extraction, save to DB, return formatted text
  POST /register-reply-id    - Bind WhatsApp reply message ID to receipt ID
  POST /confirm-receipt      - Mark receipt as CONFIRMED, return updated text with "✅ تایید شده"
  GET  /receipts             - List stored receipts
  GET  /health               - Health check
"""
import asyncio
import base64
import logging
import sys
from pathlib import Path
from typing import Optional, Dict, Any, List

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

# Ensure the project root is on sys.path so gateway/* and src/* can be imported
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from gateway.key_manager import APIKeyManager  # noqa: E402
from gateway.cache import ReceiptCacheManager  # noqa: E402
from gateway.executor import GeminiResilientExecutor  # noqa: E402
from receipt_api.formatter import format_receipt, format_receipt_confirmed  # noqa: E402
from src.db import (  # noqa: E402
    save_receipt,
    register_reply_message_id,
    confirm_receipt as db_confirm_receipt,
    list_receipts as db_list_receipts,
    get_pending_receipt,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s - %(message)s",
)
logger = logging.getLogger("receipt_api")

# Shared singletons
key_manager = APIKeyManager()
cache_manager = ReceiptCacheManager()
executor = GeminiResilientExecutor(key_manager=key_manager, cache_manager=cache_manager)

# FastAPI app
app = FastAPI(
    title="Bank Receipt Extraction API",
    description="Bridges WhatsApp Bot to Gemini Multi-Account Gateway & SQLite DB for Iranian bank receipt OCR",
    version="1.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# Request / Response Models

class ExtractRequest(BaseModel):
    image_base64: str
    mime_type: str = "image/jpeg"
    whatsapp_message_id: Optional[str] = None
    chat_id: Optional[str] = None


class ExtractResponse(BaseModel):
    success: bool
    receipt_id: str = ""
    status: str = "PENDING"
    formatted_text: str = ""
    data: dict = {}
    error: str = ""
    latency_seconds: float = 0.0
    cached: bool = False
    used_account_id: str = ""
    attempts: int = 0


class RegisterReplyRequest(BaseModel):
    receipt_id: str
    reply_message_id: str


class RegisterReplyResponse(BaseModel):
    success: bool
    error: str = ""


class ConfirmReceiptRequest(BaseModel):
    receipt_id: Optional[str] = None
    reply_message_id: Optional[str] = None
    chat_id: Optional[str] = None


class ConfirmReceiptResponse(BaseModel):
    success: bool
    receipt_id: str = ""
    status: str = ""
    updated_text: str = ""
    error: str = ""


# Endpoints

@app.get("/health")
async def health():
    """Simple health check endpoint."""
    key_metrics = await key_manager.get_all_metrics()
    active_keys = sum(1 for m in key_metrics if m.status.value == "ACTIVE")
    return {
        "status": "ok",
        "active_keys": active_keys,
        "total_keys": len(key_metrics),
    }


@app.post("/extract-receipt", response_model=ExtractResponse)
async def extract_receipt(request: ExtractRequest) -> ExtractResponse:
    """
    Accept base64 receipt image, extract details with Gemini, store in SQLite DB (PENDING),
    and return formatted Persian text + receipt_id.
    """
    try:
        image_bytes = base64.b64decode(request.image_base64)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Invalid base64 image data: {e}")

    if len(image_bytes) < 100:
        raise HTTPException(status_code=400, detail="Image data too small - likely corrupted.")

    logger.info(f"Received extraction request: {len(image_bytes)} bytes, mime={request.mime_type}")

    ocr_response = await executor.execute_receipt_ocr(
        image_bytes=image_bytes,
        mime_type=request.mime_type,
    )

    if not ocr_response.success or not ocr_response.data:
        logger.warning(f"Extraction failed: {ocr_response.error}")
        return ExtractResponse(
            success=False,
            error=ocr_response.error or "Extraction failed without specific error.",
            latency_seconds=ocr_response.latency_seconds,
            attempts=ocr_response.attempts,
        )

    data_dict = ocr_response.data.model_dump()
    formatted = format_receipt(data_dict)

    # Save to SQLite DB
    receipt_id = save_receipt(
        receipt_data=data_dict,
        formatted_text=formatted,
        whatsapp_message_id=request.whatsapp_message_id,
        chat_id=request.chat_id,
    )

    logger.info(
        f"Extraction succeeded (ID={receipt_id}) via '{ocr_response.used_account_id}' "
        f"in {ocr_response.latency_seconds}s (cached={ocr_response.cached})"
    )

    return ExtractResponse(
        success=True,
        receipt_id=receipt_id,
        status="PENDING",
        formatted_text=formatted,
        data=data_dict,
        latency_seconds=ocr_response.latency_seconds,
        cached=ocr_response.cached,
        used_account_id=ocr_response.used_account_id or "",
        attempts=ocr_response.attempts,
    )


@app.post("/register-reply-id", response_model=RegisterReplyResponse)
async def register_reply_id(request: RegisterReplyRequest) -> RegisterReplyResponse:
    """Bind WhatsApp sent reply message ID to receipt ID in SQLite DB."""
    ok = register_reply_message_id(
        receipt_id=request.receipt_id,
        reply_message_id=request.reply_message_id,
    )
    if ok:
        return RegisterReplyResponse(success=True)
    return RegisterReplyResponse(success=False, error="Receipt ID not found")


@app.post("/confirm-receipt", response_model=ConfirmReceiptResponse)
async def confirm_receipt_endpoint(request: ConfirmReceiptRequest) -> ConfirmReceiptResponse:
    """
    Mark receipt as CONFIRMED in DB and return updated text with '✅ تایید شده'.
    """
    record = db_confirm_receipt(
        receipt_id=request.receipt_id,
        reply_message_id=request.reply_message_id,
        chat_id=request.chat_id,
    )

    if not record:
        return ConfirmReceiptResponse(
            success=False,
            error="No matching pending receipt found for confirmation.",
        )

    original_text = record.get("formatted_text", "")
    confirmed_text = format_receipt_confirmed(original_text)

    logger.info(f"Receipt ID={record['id']} confirmed successfully.")

    return ConfirmReceiptResponse(
        success=True,
        receipt_id=record["id"],
        status="CONFIRMED",
        updated_text=confirmed_text,
    )


@app.get("/receipts")
async def list_stored_receipts(limit: int = 50, status: Optional[str] = None):
    """List stored receipts from database."""
    items = db_list_receipts(limit=limit, status=status)
    return {"count": len(items), "items": items}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "receipt_api.main:app",
        host="0.0.0.0",
        port=8000,
        reload=False,
        log_level="info",
    )
