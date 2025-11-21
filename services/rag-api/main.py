import json
import logging
import os
from datetime import datetime, timezone
from difflib import SequenceMatcher
from pathlib import Path
from typing import List, Tuple
from uuid import UUID

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Header
from pydantic import BaseModel
from qdrant_client import QdrantClient
from qdrant_client.http import exceptions as qdrant_exceptions
from qdrant_client.http import models as qdrant_models

load_dotenv()

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("rag-api")

app = FastAPI(title="LED Automation RAG API")
QDRANT_URL = os.getenv("QDRANT_URL")
QDRANT_API_KEY = os.getenv("QDRANT_API_KEY")
AUTOMATION_SERVICE_TOKEN = os.getenv("AUTOMATION_SERVICE_TOKEN")
OUTPUT_RESULT_LIMIT = int(os.getenv("REPORT_OUTPUT_RESULT_LIMIT", "8"))
SUPPORTED_OUTPUT_TYPES = {"penetapan", "pelaksanaan"}
DEFAULT_PENETAPAN_ALLOWED_ORDERS = {0, 5, 10, 15, 20, 25, 30, 35, 40}
DEFAULT_PENETAPAN_DOCUMENT_COLLECTION = os.getenv("PENETAPAN_DOCUMENT_COLLECTION", "denaya_rka_past_documents")
DEFAULT_PENETAPAN_HYPERLINK_COLLECTION = os.getenv("PENETAPAN_HYPERLINK_COLLECTION", "denaya_rka_past_documents_hyperlink")
HYPERLINK_COLLECTION_SUFFIX = os.getenv("HYPERLINK_COLLECTION_SUFFIX", "-hyperlink")
DEFAULT_SIMILARITY_THRESHOLD = float(os.getenv("PENETAPAN_LINK_SIMILARITY", "0.6"))

if not QDRANT_URL or not QDRANT_API_KEY:
    raise RuntimeError("QDRANT_URL and QDRANT_API_KEY must be set")

qdrant_client = QdrantClient(url=QDRANT_URL, api_key=QDRANT_API_KEY)
class OutputRequest(BaseModel):
    job_key: str
    report_id: int
    user_id: int
    metadata: dict | None = None


def fetch_reference_chunks(collection_name: str, limit: int) -> Tuple[List[qdrant_models.Record], int]:
    try:
        points, _ = qdrant_client.scroll(
            collection_name=collection_name,
            limit=limit,
            with_payload=True,
            with_vectors=False,
        )
        count_response = qdrant_client.count(collection_name=collection_name, exact=True)
        return points, count_response.count
    except qdrant_exceptions.UnexpectedResponse as exc:
        raise HTTPException(status_code=404, detail=f"Collection '{collection_name}' not found") from exc


def serialize_chunks(records: List[qdrant_models.Record]) -> List[dict]:
    serialized: List[dict] = []
    for record in records:
        payload = getattr(record, "payload", {}) or {}
        page_content = payload.get("page_content") or payload.get("text") or ""
        serialized.append(
            {
                "id": str(getattr(record, "id", "")),
                "source": payload.get("source") or payload.get("document_id"),
                "segment": page_content[:500],
                "metadata": {k: v for k, v in payload.items() if k not in {"page_content", "text"}},
            }
        )
    return serialized


def scroll_all_points(collection_name: str, required: bool = True, batch_size: int = 256) -> List[qdrant_models.Record]:
    records: List[qdrant_models.Record] = []
    offset = None
    try:
        while True:
            batch, offset = qdrant_client.scroll(
                collection_name=collection_name,
                limit=batch_size,
                with_payload=True,
                with_vectors=False,
                offset=offset,
            )
            records.extend(batch)
            if offset is None:
                break
    except qdrant_exceptions.UnexpectedResponse as exc:
        if required:
            raise HTTPException(status_code=404, detail=f"Collection '{collection_name}' not found") from exc
        logger.warning("Optional collection '%s' not found: %s", collection_name, exc)
        return []
    return records


def _coerce_allowed_orders(raw_orders) -> set[int]:
    if raw_orders is None:
        return set(DEFAULT_PENETAPAN_ALLOWED_ORDERS)
    if isinstance(raw_orders, (set, list, tuple)):
        values = raw_orders
    elif isinstance(raw_orders, str):
        values = [item.strip() for item in raw_orders.split(',') if item.strip()]
    else:
        return set(DEFAULT_PENETAPAN_ALLOWED_ORDERS)
    coerced: set[int] = set()
    for value in values:
        try:
            coerced.add(int(value))
        except (TypeError, ValueError):
            continue
    return coerced or set(DEFAULT_PENETAPAN_ALLOWED_ORDERS)


def _coerce_reference_files(source) -> List[str]:
    if source is None:
        return []
    if isinstance(source, str):
        return [source]
    if isinstance(source, (list, tuple, set)):
        return [str(item) for item in source if str(item).strip()]
    return []


def _extract_order(payload: dict, metadata_payload: dict) -> int | None:
    value = metadata_payload.get("order")
    if value is None:
        value = payload.get("order")
    try:
        return int(value)
    except (TypeError, ValueError):
        return value


def _discover_reference_files(report_uuid: str, metadata: dict | None) -> List[str]:
    metadata = metadata or {}
    explicit = _coerce_reference_files(
        metadata.get("reference_files")
        or metadata.get("reference_filenames")
        or metadata.get("files")
    )
    if explicit:
        return explicit

    records = scroll_all_points(report_uuid, required=False)
    filenames: List[str] = []
    seen: set[str] = set()
    for record in records:
        payload = getattr(record, "payload", {}) or {}
        metadata_payload = payload.get("metadata") or {}
        source = metadata_payload.get("source") or payload.get("source") or payload.get("document_id")
        if not source:
            continue
        filename = Path(str(source)).name or str(source)
        if filename and filename not in seen:
            seen.add(filename)
            filenames.append(filename)

    if not filenames:
        logger.info("No reference filenames discovered for collection '%s'", report_uuid)

    return filenames


def build_penetapan_output(report_uuid: str, metadata: dict | None) -> tuple[dict, dict]:
    metadata = metadata or {}
    document_collection = str(
        metadata.get("document_collection")
        or DEFAULT_PENETAPAN_DOCUMENT_COLLECTION
        or report_uuid
    )
    hyperlink_collection = str(
        metadata.get("hyperlink_collection")
        or DEFAULT_PENETAPAN_HYPERLINK_COLLECTION
        or f"{document_collection}{HYPERLINK_COLLECTION_SUFFIX}"
    )
    allowed_orders = _coerce_allowed_orders(metadata.get("allowed_orders"))
    reference_files = _discover_reference_files(report_uuid, metadata)
    similarity_threshold = float(metadata.get("similarity_threshold") or DEFAULT_SIMILARITY_THRESHOLD)

    document_points = scroll_all_points(document_collection, required=True)
    if not document_points:
        raise HTTPException(status_code=404, detail="No penetapan chunks available")

    penetapan_entries: List[dict] = []
    for point in document_points:
        payload = getattr(point, "payload", {}) or {}
        metadata_payload = payload.get("metadata") or {}
        query_text = payload.get("text") or payload.get("page_content") or ""
        order_value = _extract_order(payload, metadata_payload)
        entry = {
            "query_source_document": metadata_payload.get("source") or payload.get("source") or payload.get("document_id"),
            "query_text": query_text,
            "heading": metadata_payload.get("heading"),
            "order": order_value,
        }
        if not allowed_orders or order_value in allowed_orders:
            penetapan_entries.append(entry)

    penetapan_entries.sort(key=lambda item: item.get("order") or 0)

    hyperlink_points = scroll_all_points(hyperlink_collection, required=False)
    hyperlink_map: dict[str, List[dict]] = {}
    for point in hyperlink_points:
        payload = getattr(point, "payload", {}) or {}
        metadata_payload = payload.get("metadata") or {}
        heading = metadata_payload.get("heading")
        if not heading:
            continue
        order_value = _extract_order(payload, metadata_payload)
        entry = {
            "page_content/title": payload.get("text") or payload.get("page_content") or "",
            "heading": heading,
            "order": order_value,
            "link": metadata_payload.get("link"),
        }
        hyperlink_map.setdefault(heading, []).append(entry)

    penetapan_hyperlink: List[dict] = []
    total_links = 0
    for entry in penetapan_entries:
        heading = entry.get("heading")
        old_references = [dict(item) for item in hyperlink_map.get(heading, [])]
        total_links += len(old_references)

        document_payload = {
            "query_text": entry["query_text"],
            "order": entry.get("order"),
            "query_source_document": entry.get("query_source_document"),
            "number_of_links": len(old_references),
            "old_reference_list": old_references,
        }
        if heading:
            document_payload["heading"] = heading

        unmatched_documents: set[str] = set()
        matched_files: set[str] = set()
        if reference_files and old_references:
            for link in old_references:
                text_to_match = link.get("page_content/title") or ""
                best_match = None
                highest_score = 0.0
                for candidate in reference_files:
                    score = SequenceMatcher(None, text_to_match.lower(), candidate.lower()).ratio()
                    if score > highest_score:
                        highest_score = score
                        best_match = candidate
                if best_match and highest_score >= similarity_threshold:
                    matched_files.add(best_match)
                else:
                    if text_to_match:
                        unmatched_documents.add(text_to_match)
        document_payload["new_reference_list"] = sorted(matched_files)
        if unmatched_documents:
            document_payload["documents_with_unmatched_links"] = sorted(unmatched_documents)

        flattened_references: List[str] = []
        for ref in old_references:
            if isinstance(ref, dict) and ref.get("page_content/title"):
                flattened_references.append(ref["page_content/title"])
            elif isinstance(ref, str):
                flattened_references.append(ref)
        document_payload["old_reference_list"] = flattened_references

        penetapan_hyperlink.append(document_payload)

    payload = {
        "summary": f"Generated {len(penetapan_hyperlink)} penetapan entries with hyperlink mapping.",
        "results": penetapan_hyperlink,
    }
    meta = {
        "document_collection": document_collection,
        "hyperlink_collection": hyperlink_collection if hyperlink_points else None,
        "allowed_orders": sorted(allowed_orders),
        "reference_files_used": reference_files,
        "penetapan_records": len(penetapan_entries),
        "hyperlink_records": len(hyperlink_points),
        "total_links_processed": total_links,
        "chunks_returned": len(penetapan_hyperlink),
    }
    meta = {key: value for key, value in meta.items() if value not in ({}, [], None)}
    return payload, meta


def build_default_output(collection_name: str, normalized_type: str, limit_override: int | None = None) -> tuple[dict, dict]:
    limit = limit_override or OUTPUT_RESULT_LIMIT
    records, total_chunks = fetch_reference_chunks(collection_name, limit)
    if not records:
        raise HTTPException(status_code=404, detail="No chunks stored for this report")

    chunks = serialize_chunks(records)
    payload = {
        "summary": f"Retrieved {len(chunks)} reference chunks for {normalized_type} review.",
        "results": chunks,
    }
    meta = {
        "chunks_returned": len(chunks),
        "total_chunks": total_chunks,
        "result_limit": limit,
    }
    return payload, meta


@app.post("/reports/{report_uuid}/outputs/{output_type}")
async def create_report_output(
    report_uuid: str,
    output_type: str,
    request: OutputRequest,
    authorization: str | None = Header(default=None),
):
    try:
        normalized_uuid = str(UUID(report_uuid))
    except (ValueError, TypeError) as exc:
        raise HTTPException(status_code=422, detail="Invalid report UUID") from exc

    normalized_type = output_type.lower()
    if normalized_type not in SUPPORTED_OUTPUT_TYPES:
        raise HTTPException(status_code=422, detail="Unsupported output type")

    if AUTOMATION_SERVICE_TOKEN and authorization != f"Bearer {AUTOMATION_SERVICE_TOKEN}":
        raise HTTPException(status_code=401, detail="Invalid automation token")

    request_metadata = request.metadata or {}
    limit_override = request_metadata.get("result_limit")
    if isinstance(limit_override, str) and limit_override.isdigit():
        limit_override = int(limit_override)
    elif not isinstance(limit_override, int):
        limit_override = None

    if normalized_type == "penetapan":
        payload, payload_meta = build_penetapan_output(normalized_uuid, request_metadata)
    else:
        payload, payload_meta = build_default_output(normalized_uuid, normalized_type, limit_override)

    generated_at = datetime.now(timezone.utc).isoformat()
    meta = {
        "generated_at": generated_at,
        "job_key": request.job_key,
        "report_id": request.report_id,
        "user_id": request.user_id,
        "output_type": normalized_type,
    }
    meta.update(payload_meta)

    return {
        "status": "completed",
        "payload": payload,
        "meta": meta,
    }


@app.get("/health")
async def health_check():
    return {"status": "ok"}
