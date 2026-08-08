import os
import time
import logging
from typing import List, Optional
from fastapi import FastAPI, File, UploadFile, Form, HTTPException, BackgroundTask
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware

from gateway.config import settings
from gateway.models import APIKeyMetrics, OCRResponse, BankReceiptData
from gateway.key_manager import APIKeyManager
from gateway.cache import ReceiptCacheManager
from gateway.executor import GeminiResilientExecutor
from gateway.database import GatewayDatabase

# Configure Logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"
)
logger = logging.getLogger("gemini_gateway.main")

app = FastAPI(
    title="Gemini API Multi-Account Gateway",
    description="High-availability API key pool manager and bank receipt OCR processing gateway.",
    version="1.0.0"
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Global Manager Instances
key_manager = APIKeyManager()
cache_manager = ReceiptCacheManager(ttl_seconds=settings.cache_ttl_seconds)
executor = GeminiResilientExecutor(key_manager=key_manager, cache_manager=cache_manager)
db = GatewayDatabase()


@app.get("/health")
async def health_check():
    """Health check endpoint."""
    metrics = await key_manager.get_all_metrics()
    active_keys = sum(1 for m in metrics if m.status == "ACTIVE")
    return {
        "status": "healthy",
        "timestamp": time.time(),
        "total_keys": len(metrics),
        "active_keys": active_keys,
        "model": settings.model_name
    }


@app.post("/api/v1/ocr/extract", response_model=OCRResponse)
async def extract_receipt_ocr(
    file: Optional[UploadFile] = File(None),
    max_retries: Optional[int] = Form(None)
):
    """Process bank receipt image OCR using intelligent key rotation and automatic failover."""
    if not file:
        raise HTTPException(status_code=400, detail="Image file must be provided.")

    image_bytes = await file.read()
    mime_type = file.content_type or "image/jpeg"

    if len(image_bytes) == 0:
        raise HTTPException(status_code=400, detail="Uploaded file is empty.")

    # Execute resilient OCR
    result: OCRResponse = await executor.execute_receipt_ocr(
        image_bytes=image_bytes,
        mime_type=mime_type,
        max_retries=max_retries
    )

    # Save to database in background
    image_hash = cache_manager.compute_image_hash(image_bytes)
    await db.save_ocr_record(
        image_hash=image_hash,
        used_account_id=result.used_account_id,
        success=result.success,
        cached=result.cached,
        attempts=result.attempts,
        latency_seconds=result.latency_seconds,
        ocr_data=result.data.model_dump() if result.data else None,
        error_msg=result.error
    )

    return result


@app.get("/api/v1/keys/status", response_model=List[APIKeyMetrics])
async def get_key_status():
    """Retrieve detailed real-time metrics and health scores for all Gemini API keys."""
    return await key_manager.get_all_metrics()


@app.post("/api/v1/keys/{account_id}/reset")
async def reset_key(account_id: str):
    """Manually reset a key's status back to ACTIVE."""
    success = await key_manager.reset_key_status(account_id)
    if not success:
        raise HTTPException(status_code=404, detail=f"Key {account_id} not found.")
    await db.log_key_event(account_id, "MANUAL_RESET", "Key status manually restored to ACTIVE.")
    return {"message": f"Key {account_id} successfully reset to ACTIVE."}


@app.get("/api/v1/history")
async def get_ocr_history(limit: int = 30):
    """Retrieve recent OCR extraction history."""
    return await db.get_recent_ocr_records(limit=limit)


@app.get("/dashboard", response_class=HTMLResponse)
async def get_monitoring_dashboard():
    """Modern HTML/JS Web Dashboard for real-time monitoring of key pool health and OCR operations."""
    html_content = """
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Gemini API Multi-Account Gateway Dashboard</title>
        <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
        <link href="https://cdn.jsdelivr.net/npm/bootstrap-icons@1.10.5/font/bootstrap-icons.css" rel="stylesheet">
        <style>
            body { background-color: #0f172a; color: #f8fafc; font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; }
            .navbar { background-color: #1e293b; border-bottom: 1px solid #334155; }
            .card { background-color: #1e293b; border: 1px solid #334155; border-radius: 12px; }
            .status-badge-ACTIVE { background-color: #10b981; color: white; }
            .status-badge-COOLDOWN { background-color: #f59e0b; color: white; }
            .status-badge-RATE_LIMITED { background-color: #ef4444; color: white; }
            .status-badge-DISABLED { background-color: #64748b; color: white; }
            .table-dark { background-color: #1e293b; color: #f8fafc; }
            .table-dark th { border-color: #334155; background-color: #0f172a; }
            .table-dark td { border-color: #334155; vertical-align: middle; }
            .metric-card { text-align: center; padding: 20px; }
            .metric-value { font-size: 2.2rem; font-weight: bold; }
            .btn-reset { padding: 2px 8px; font-size: 0.8rem; }
        </style>
    </head>
    <body>
        <nav class="navbar navbar-dark px-4 py-3">
            <a class="navbar-brand d-flex align-items-center" href="#">
                <i class="bi bi-cpu-fill text-primary me-2 fs-3"></i>
                <span class="fw-bold fs-4">Gemini API Multi-Account Gateway</span>
            </a>
            <span class="badge bg-primary fs-6" id="model-badge">Model: Loading...</span>
        </nav>

        <div class="container-fluid p-4">
            <!-- Top Summary Cards -->
            <div class="row g-3 mb-4">
                <div class="col-md-3">
                    <div class="card metric-card">
                        <div class="text-secondary mb-1">Total API Keys</div>
                        <div class="metric-value text-info" id="total-keys">0</div>
                    </div>
                </div>
                <div class="col-md-3">
                    <div class="card metric-card">
                        <div class="text-secondary mb-1">Active Healthy Keys</div>
                        <div class="metric-value text-success" id="active-keys">0</div>
                    </div>
                </div>
                <div class="col-md-3">
                    <div class="card metric-card">
                        <div class="text-secondary mb-1">Keys in Cooldown</div>
                        <div class="metric-value text-warning" id="cooldown-keys">0</div>
                    </div>
                </div>
                <div class="col-md-3">
                    <div class="card metric-card">
                        <div class="text-secondary mb-1">Total Requests Served</div>
                        <div class="metric-value text-light" id="total-requests">0</div>
                    </div>
                </div>
            </div>

            <!-- Main Keys Table -->
            <div class="card p-3 mb-4">
                <div class="d-flex justify-content-between align-items-center mb-3">
                    <h5 class="mb-0 fw-bold"><i class="bi bi-key-fill text-warning me-2"></i>API Key Pool Metrics</h5>
                    <button class="btn btn-sm btn-outline-primary" onclick="loadDashboardData()"><i class="bi bi-arrow-clockwise me-1"></i>Refresh</button>
                </div>
                <div class="table-responsive">
                    <table class="table table-dark table-hover align-middle mb-0">
                        <thead>
                            <tr>
                                <th>Account ID</th>
                                <th>API Key</th>
                                <th>Status</th>
                                <th>Score</th>
                                <th>Total Req</th>
                                <th>Success / Fail</th>
                                <th>429 Rate Limits</th>
                                <th>Avg Latency</th>
                                <th>Cooldown Until</th>
                                <th>Actions</th>
                            </tr>
                        </thead>
                        <tbody id="keys-tbody">
                            <tr><td colspan="10" class="text-center py-4 text-secondary">Loading API Key pool data...</td></tr>
                        </tbody>
                    </table>
                </div>
            </div>

            <!-- OCR Test Upload Form -->
            <div class="row g-3">
                <div class="col-md-6">
                    <div class="card p-4">
                        <h5 class="mb-3 fw-bold"><i class="bi bi-file-earmark-image text-success me-2"></i>Test Receipt OCR Extraction</h5>
                        <form id="ocr-form" onsubmit="submitOCR(event)">
                            <div class="mb-3">
                                <label class="form-label text-secondary">Upload Receipt Image (JPEG, PNG)</label>
                                <input type="file" id="ocr-file" class="form-control bg-dark text-light border-secondary" required accept="image/*">
                            </div>
                            <button type="submit" class="btn btn-success w-100 fw-bold" id="ocr-submit-btn">
                                <i class="bi bi-lightning-charge me-1"></i>Process OCR via Gateway
                            </button>
                        </form>
                    </div>
                </div>

                <div class="col-md-6">
                    <div class="card p-4">
                        <h5 class="mb-3 fw-bold"><i class="bi bi-code-square text-info me-2"></i>JSON Output Result</h5>
                        <pre id="json-output" class="bg-dark p-3 rounded text-success border border-secondary" style="max-height: 300px; overflow-y: auto;">Submit a receipt image to view extracted JSON output...</pre>
                    </div>
                </div>
            </div>
        </div>

        <script>
            async function loadDashboardData() {
                try {
                    const healthResp = await fetch('/health');
                    const health = await healthResp.json();
                    document.getElementById('model-badge').innerText = 'Model: ' + health.model;

                    const keysResp = await fetch('/api/v1/keys/status');
                    const keys = await keysResp.json();

                    let totalKeys = keys.length;
                    let activeKeys = 0;
                    let cooldownKeys = 0;
                    let totalRequests = 0;

                    let tbodyHtml = '';
                    const now = Date.now() / 1000;

                    keys.forEach(k => {
                        if (k.status === 'ACTIVE') activeKeys++;
                        if (k.status === 'COOLDOWN' || k.status === 'RATE_LIMITED') cooldownKeys++;
                        totalRequests += k.total_requests;

                        let cooldownText = '-';
                        if (k.cooldown_until && k.cooldown_until > now) {
                            let rem = Math.ceil(k.cooldown_until - now);
                            cooldownText = rem + 's remaining';
                        }

                        tbodyHtml += `
                            <tr>
                                <td class="fw-bold">${k.account_id}</td>
                                <td><code>${k.api_key_masked}</code></td>
                                <td><span class="badge status-badge-${k.status}">${k.status}</span></td>
                                <td class="fw-bold text-info">${k.score}</td>
                                <td>${k.total_requests}</td>
                                <td><span class="text-success">${k.successful_requests}</span> / <span class="text-danger">${k.failed_requests}</span></td>
                                <td class="text-warning fw-bold">${k.rate_limit_errors}</td>
                                <td>${k.average_response_time}s</td>
                                <td class="text-warning">${cooldownText}</td>
                                <td>
                                    <button class="btn btn-outline-warning btn-reset" onclick="resetKey('${k.account_id}')">Reset</button>
                                </td>
                            </tr>
                        `;
                    });

                    document.getElementById('total-keys').innerText = totalKeys;
                    document.getElementById('active-keys').innerText = activeKeys;
                    document.getElementById('cooldown-keys').innerText = cooldownKeys;
                    document.getElementById('total-requests').innerText = totalRequests;
                    document.getElementById('keys-tbody').innerHTML = tbodyHtml || '<tr><td colspan="10" class="text-center py-3">No keys configured in .env</td></tr>';
                } catch (err) {
                    console.error('Error fetching dashboard data:', err);
                }
            }

            async function resetKey(accId) {
                if (confirm('Reset status for ' + accId + ' to ACTIVE?')) {
                    await fetch('/api/v1/keys/' + accId + '/reset', { method: 'POST' });
                    loadDashboardData();
                }
            }

            async function submitOCR(e) {
                e.preventDefault();
                const fileInput = document.getElementById('ocr-file');
                if (!fileInput.files[0]) return;

                const submitBtn = document.getElementById('ocr-submit-btn');
                const jsonOutput = document.getElementById('json-output');

                submitBtn.disabled = true;
                submitBtn.innerText = 'Processing with Gemini Gateway...';
                jsonOutput.innerText = 'Running OCR extraction...';

                const formData = new FormData();
                formData.append('file', fileInput.files[0]);

                try {
                    const resp = await fetch('/api/v1/ocr/extract', {
                        method: 'POST',
                        body: formData
                    });
                    const resJson = await resp.json();
                    jsonOutput.innerText = JSON.stringify(resJson, null, 2);
                    loadDashboardData();
                } catch (err) {
                    jsonOutput.innerText = 'Error: ' + err;
                } finally {
                    submitBtn.disabled = false;
                    submitBtn.innerHTML = '<i class="bi bi-lightning-charge me-1"></i>Process OCR via Gateway';
                }
            }

            // Auto-refresh every 5 seconds
            setInterval(loadDashboardData, 5000);
            loadDashboardData();
        </script>
    </body>
    </html>
    """
    return HTMLResponse(content=html_content)
