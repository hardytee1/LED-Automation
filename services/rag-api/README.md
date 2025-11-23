# RAG Automation API

FastAPI service that powers the LED automation workflows for Penetapan and Pelaksanaan outputs. The service exposes a single endpoint that Laravel hits whenever a report snapshot needs refreshed:

- `POST /reports/{report_uuid}/outputs/{type}`

Where `{type}` is currently `penetapan` or `pelaksanaan`.

## Pelaksanaan metadata overrides

The POST body accepts a `metadata` object. When requesting a Pelaksanaan snapshot you can override the defaults without redeploying the service:

| Metadata key | Description |
| --- | --- |
| `pelaksanaan_document_collection` | Qdrant collection containing the past narrative chunks (defaults to `PELAKSANAAN_DOCUMENT_COLLECTION`). |
| `pelaksanaan_hyperlink_collection` | Optional collection that stores hyperlink/title payloads for each heading. |
| `pelaksanaan_allowed_orders` | Comma-delimited string or array of integers indicating which narrative orders to keep (defaults to `{1, 6, 11, ...}`). |
| `pelaksanaan_section_collections` | JSON/dict mapping narrative indices to `[reference_collection, new_reference_collection]`. |
| `reference_top_k` / `nested_reference_top_k` | Control how many matches are retrieved per chunk at each stage (defaults to the env values). |
| `include_debug` | Set to `true` to include diagnostics (`title_matches`, `chunks_processed`) in the payload. |

## Local development

```powershell
cd services/rag-api
uv sync
uv run uvicorn main:app --reload --port 8002
```

Populate `.env` (see `.env.example`) with your Qdrant credentials plus the optional Pelaksanaan knobs. Use `uv run python -m py_compile main.py` to catch syntax issues before deploying.
