"""
Unit tests for FastAPI endpoints: health, extract, register-reply-id, confirm-receipt, receipts list.
"""
import base64
from unittest.mock import AsyncMock, patch
from fastapi.testclient import TestClient
from receipt_api.main import app
from src.schemas import BankReceiptData
from gateway.executor import OCRResponse

client = TestClient(app)


def test_health_endpoint():
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert "active_keys" in data


def test_full_api_receipt_workflow():
    mock_receipt = BankReceiptData(
        amount=1500000,
        tracking_id="12345678",
        source_bank="ملت",
        destination_bank="پاسارگاد",
        transaction_status="موفق",
        confidence_score=0.95,
    )
    mock_ocr = OCRResponse(
        success=True,
        data=mock_receipt.model_dump(),
        latency_seconds=0.45,
        used_account_id="test_acc",
    )

    # 1. Test POST /extract-receipt
    dummy_image = base64.b64encode(b"A" * 200).decode("utf-8")
    with patch("receipt_api.main.executor.execute_receipt_ocr", new_callable=AsyncMock) as mock_exec:
        mock_exec.return_value = mock_ocr

        resp = client.post(
            "/extract-receipt",
            json={
                "image_base64": dummy_image,
                "mime_type": "image/jpeg",
                "chat_id": "test_chat_123",
            },
        )
        assert resp.status_code == 200
        res_data = resp.json()
        assert res_data["success"] is True
        assert res_data["status"] == "PENDING"
        receipt_id = res_data["receipt_id"]
        assert receipt_id != ""
        assert "اطلاعات فیش بانکی" in res_data["formatted_text"]
        assert "1,500,000 ریال" in res_data["formatted_text"]

    # 2. Test POST /register-reply-id
    reply_msg_id = "wamid.BOT_MSG_999"
    resp_reg = client.post(
        "/register-reply-id",
        json={"receipt_id": receipt_id, "reply_message_id": reply_msg_id},
    )
    assert resp_reg.status_code == 200
    assert resp_reg.json()["success"] is True

    # 3. Test POST /confirm-receipt
    resp_conf = client.post(
        "/confirm-receipt",
        json={"reply_message_id": reply_msg_id},
    )
    assert resp_conf.status_code == 200
    conf_data = resp_conf.json()
    assert conf_data["success"] is True
    assert conf_data["status"] == "CONFIRMED"
    assert "✅ *تایید شده*" in conf_data["updated_text"]

    # 4. Test GET /receipts
    resp_list = client.get("/receipts")
    assert resp_list.status_code == 200
    list_data = resp_list.json()
    assert list_data["count"] >= 1
