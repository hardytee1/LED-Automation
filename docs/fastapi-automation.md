# FastAPI Automation Service Stub

This project expects an automation API (FastAPI or similar) that receives retrieval jobs for Penetapan/Pelaksanaan outputs. The Laravel app queues these jobs through `RetrieveReportOutput`, which POSTs to:

```
POST {AUTOMATION_SERVICE_URL}/reports/{report_uuid}/outputs/{type}
```

## Expected Request Body

```json
{
    "job_key": "uuid-tied-to-laravel-job",
    "report_id": 12,
    "user_id": 4,
    "metadata": { "custom": "values" }
}
```

## Expected Response Body

```json
{
    "status": "completed",
    "payload": { "summary": "...", "results": [...] },
    "meta": { "duration_ms": 4000 }
}
```

Return HTTP 202 while still processing or 200 when the JSON is ready. For failures, send a 4xx/5xx with an error body; Laravel will mark the report snapshot as failed.

## Environment Variables

Configure the Laravel app:

```
AUTOMATION_SERVICE_URL=http://127.0.0.1:9000
AUTOMATION_SERVICE_TOKEN=optional-shared-secret
AUTOMATION_SERVICE_TIMEOUT=240
REPORT_OUTPUT_QUEUE=penetapan
```

## Local FastAPI Stub

Create `automation_service.py`:

```python
from fastapi import FastAPI, Header, HTTPException
from pydantic import BaseModel

app = FastAPI()
SECRET = "optional-shared-secret"

class OutputRequest(BaseModel):
    job_key: str
    report_id: int
    user_id: int
    metadata: dict | None = None

@app.post("/reports/{report_uuid}/outputs/{output_type}")
async def retrieve_output(report_uuid: str, output_type: str, data: OutputRequest, authorization: str | None = Header(default=None)):
    if SECRET and authorization != f"Bearer {SECRET}":
        raise HTTPException(status_code=401, detail="Invalid token")

    # TODO: trigger real processing (Qdrant, OpenAI, etc.)
    payload = {
        "summary": f"Stub result for {output_type} report {report_uuid}",
        "records": [
            {"title": "Example", "score": 0.98}
        ]
    }

    return {
        "status": "completed",
        "payload": payload,
        "meta": {"duration_ms": 1500}
    }
```

Install dependencies:

```
python -m venv .venv
.venv\Scripts\activate
pip install fastapi uvicorn
```

Run the stub:

```
uvicorn automation_service:app --host 127.0.0.1 --port 9000 --reload
```

## Workflow Recap

1. User clicks *Retrieve Penetapan/Pelaksanaan* in the UI.
2. Laravel dispatches `RetrieveReportOutput` to the `REPORT_OUTPUT_QUEUE` (no intermediate DB rows).
3. The job POSTs to the FastAPI endpoint with the report UUID, type, and metadata.
4. FastAPI processes the request and returns the JSON payload plus optional meta.
5. Laravel stores the latest response JSON directly on the `reports` table for display.

Extend the stub to stream progress, push artifacts to S3/local storage, or callback to Laravel if long-running work is required.
