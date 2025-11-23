import json
import logging
import os
from datetime import datetime, timezone
from difflib import SequenceMatcher
from functools import lru_cache
from pathlib import Path
from typing import Dict, List, Tuple
from uuid import UUID

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Header
from langchain_community.vectorstores import Qdrant as VectorStoreQdrant
from langchain_core.documents import Document
from langchain_huggingface import HuggingFaceEmbeddings
from langchain_text_splitters import RecursiveCharacterTextSplitter
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
EMBEDDING_MODEL_NAME = os.getenv("EMBEDDING_MODEL", "all-MiniLM-L6-v2")
CHUNK_SIZE = int(os.getenv("CHUNK_SIZE", "1000"))
CHUNK_OVERLAP = int(os.getenv("CHUNK_OVERLAP", "200"))
DEFAULT_PELAKSANAAN_ALLOWED_ORDERS = {1, 6, 11, 16, 21, 26, 31, 36, 41}
DEFAULT_PELAKSANAAN_DOCUMENT_COLLECTION = os.getenv(
    "PELAKSANAAN_DOCUMENT_COLLECTION",
    DEFAULT_PENETAPAN_DOCUMENT_COLLECTION,
)
DEFAULT_PELAKSANAAN_HYPERLINK_COLLECTION = os.getenv(
    "PELAKSANAAN_HYPERLINK_COLLECTION",
    DEFAULT_PENETAPAN_HYPERLINK_COLLECTION,
)
DEFAULT_PELAKSANAAN_SECTION_COLLECTIONS: Dict[int, Tuple[str, str]] = {
    0: ("rka_2_1", "rpl_2_1"),
    2: ("rka_2_2", "rpl_2_2"),
    3: ("rka_2_3", "rpl_2_3"),
    4: ("rka_2_4", "rpl_2_4"),
    5: ("rka_2_5", "rpl_2_5"),
    6: ("rka_2_6", "rpl_2_6"),
    7: ("rka_2_7", "rpl_2_7"),
    8: ("rka_2_8", "rpl_2_8"),
    9: ("rka_2_9", "rpl_2_9"),
}
PELAKSANAAN_REFERENCE_TOP_K = int(os.getenv("PELAKSANAAN_REFERENCE_TOP_K", "1"))
PELAKSANAAN_NESTED_TOP_K = int(os.getenv("PELAKSANAAN_NESTED_TOP_K", "1"))

if not QDRANT_URL:
    raise RuntimeError("QDRANT_URL must be set")

if not QDRANT_API_KEY:
    logger.warning("QDRANT_API_KEY is not set; assuming local Qdrant without authentication")

qdrant_client = QdrantClient(url=QDRANT_URL, api_key=QDRANT_API_KEY or None)


@lru_cache(maxsize=1)
def get_embedding_model() -> HuggingFaceEmbeddings:
    if not EMBEDDING_MODEL_NAME:
        raise RuntimeError("EMBEDDING_MODEL must be defined for pelaksanaan processing")
    return HuggingFaceEmbeddings(model_name=EMBEDDING_MODEL_NAME)


@lru_cache(maxsize=1)
def get_semantic_chunker() -> RecursiveCharacterTextSplitter:
    chunk_size = max(1, CHUNK_SIZE)
    chunk_overlap = max(0, min(chunk_size - 1, CHUNK_OVERLAP))
    return RecursiveCharacterTextSplitter(chunk_size=chunk_size, chunk_overlap=chunk_overlap)


def _build_vectorstore(collection_name: str) -> VectorStoreQdrant:
    try:
        return VectorStoreQdrant(
            client=qdrant_client,
            collection_name=collection_name,
            embeddings=get_embedding_model(),
        )
    except qdrant_exceptions.UnexpectedResponse as exc:
        raise HTTPException(status_code=404, detail=f"Collection '{collection_name}' not found") from exc
    except Exception as exc:  # pragma: no cover - defensive guard
        logger.exception("Failed to initialize vectorstore for %s", collection_name)
        raise HTTPException(status_code=500, detail="Failed to prepare vectorstore") from exc


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


def _coerce_allowed_orders(raw_orders, default: set[int]) -> set[int]:
    if raw_orders is None:
        return set(default)
    if isinstance(raw_orders, (set, list, tuple)):
        values = raw_orders
    elif isinstance(raw_orders, str):
        values = [item.strip() for item in raw_orders.split(',') if item.strip()]
    else:
        return set(default)
    coerced: set[int] = set()
    for value in values:
        try:
            coerced.add(int(value))
        except (TypeError, ValueError):
            continue
    return coerced or set(default)


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


def _coerce_positive_int(value, fallback: int, minimum: int = 1) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return max(minimum, fallback)
    return max(minimum, parsed)


def _coerce_section_collections(raw_map, default_map: Dict[int, Tuple[str, str]]) -> Dict[int, Tuple[str, str]]:
    if not raw_map:
        return dict(default_map)

    parsed = raw_map
    if isinstance(raw_map, str):
        try:
            parsed = json.loads(raw_map)
        except json.JSONDecodeError:
            logger.warning("Invalid JSON for section collections override: %s", raw_map)
            return dict(default_map)

    items: List[Tuple[int, object]] = []
    if isinstance(parsed, dict):
        for key, value in parsed.items():
            try:
                items.append((int(key), value))
            except (TypeError, ValueError):
                continue
    elif isinstance(parsed, list):
        items = list(enumerate(parsed))
    else:
        logger.warning("Unsupported type for section collection override: %s", type(parsed))
        return dict(default_map)

    coerced: Dict[int, Tuple[str, str]] = {}
    for index, value in items:
        ref_col = None
        new_col = None
        if isinstance(value, (list, tuple)):
            if len(value) >= 2:
                ref_col = str(value[0]).strip() or None
                new_col = str(value[1]).strip() or None
        elif isinstance(value, dict):
            ref_col = str(
                value.get("reference")
                or value.get("reference_collection")
                or value.get("rka")
                or value.get("source")
                or ""
            ).strip() or None
            new_col = str(
                value.get("new")
                or value.get("new_collection")
                or value.get("rpl")
                or value.get("target")
                or ""
            ).strip() or None
        elif isinstance(value, str) and '|' in value:
            candidates = [part.strip() for part in value.split('|', 1)]
            if len(candidates) == 2:
                ref_col, new_col = candidates

        if ref_col and new_col:
            coerced[index] = (ref_col, new_col)

    return coerced or dict(default_map)


def _extract_nested_reference_content(retrieval_results: List[dict]) -> str | None:
    for result in retrieval_results:
        nested_results = result.get("nested_search_results") or []
        for nested in nested_results:
            content = nested.get("page_content") or nested.get("content")
            if content:
                return content
    return None


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
    allowed_orders = _coerce_allowed_orders(metadata.get("allowed_orders"), DEFAULT_PENETAPAN_ALLOWED_ORDERS)
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


def build_pelaksanaan_output(report_uuid: str, metadata: dict | None) -> tuple[dict, dict]:
    metadata = metadata or {}
    document_collection = str(
        metadata.get("pelaksanaan_document_collection")
        or metadata.get("document_collection")
        or DEFAULT_PELAKSANAAN_DOCUMENT_COLLECTION
        or report_uuid
    )
    hyperlink_collection = str(
        metadata.get("pelaksanaan_hyperlink_collection")
        or metadata.get("hyperlink_collection")
        or DEFAULT_PELAKSANAAN_HYPERLINK_COLLECTION
        or f"{document_collection}{HYPERLINK_COLLECTION_SUFFIX}"
    )
    allowed_orders = _coerce_allowed_orders(
        metadata.get("pelaksanaan_allowed_orders") or metadata.get("allowed_orders"),
        DEFAULT_PELAKSANAAN_ALLOWED_ORDERS,
    )
    section_collections = _coerce_section_collections(
        metadata.get("pelaksanaan_section_collections") or metadata.get("section_collections"),
        DEFAULT_PELAKSANAAN_SECTION_COLLECTIONS,
    )
    include_debug = bool(metadata.get("include_debug"))
    reference_top_k = _coerce_positive_int(
        metadata.get("reference_top_k") or metadata.get("pelaksanaan_reference_top_k"),
        PELAKSANAAN_REFERENCE_TOP_K,
    )
    nested_top_k = _coerce_positive_int(
        metadata.get("nested_reference_top_k") or metadata.get("pelaksanaan_nested_reference_top_k"),
        PELAKSANAAN_NESTED_TOP_K,
    )

    document_points = scroll_all_points(document_collection, required=True)
    if not document_points:
        raise HTTPException(status_code=404, detail="No pelaksanaan narratives available")

    penetapan_entries: List[dict] = []
    heading_to_query_map: Dict[str, str] = {}
    for point in document_points:
        payload = getattr(point, "payload", {}) or {}
        metadata_payload = payload.get("metadata") or {}
        query_text = payload.get("text") or payload.get("page_content") or ""
        if not query_text:
            continue
        order_value = _extract_order(payload, metadata_payload)
        if allowed_orders and order_value not in allowed_orders:
            continue
        heading = metadata_payload.get("heading")
        entry = {
            "query_source_document": metadata_payload.get("source") or payload.get("source") or payload.get("document_id"),
            "query_text": query_text,
            "heading": heading,
            "order": order_value,
        }
        if heading and heading not in heading_to_query_map:
            heading_to_query_map[heading] = query_text
        penetapan_entries.append(entry)

    penetapan_entries.sort(key=lambda item: item.get("order") or 0)
    if not penetapan_entries:
        raise HTTPException(status_code=404, detail="No pelaksanaan entries matched the allowed orders")

    hyperlink_points = scroll_all_points(hyperlink_collection, required=False)
    hyperlink_map: Dict[str, List[dict]] = {}
    for point in hyperlink_points:
        payload = getattr(point, "payload", {}) or {}
        metadata_payload = payload.get("metadata") or {}
        heading = metadata_payload.get("heading")
        if not heading:
            continue
        entry = {
            "page_content/title": payload.get("text") or payload.get("page_content") or "",
            "heading": heading,
            "order": _extract_order(payload, metadata_payload),
        }
        hyperlink_map.setdefault(heading, []).append(entry)
    for items in hyperlink_map.values():
        items.sort(key=lambda item: item.get("order") or 0)

    penetapan_hyperlink: List[dict] = []
    for entry in penetapan_entries:
        heading = entry.get("heading")
        old_references = [dict(item) for item in hyperlink_map.get(heading, [])]
        penetapan_hyperlink.append(
            {
                "heading": heading,
                "order": entry.get("order"),
                "original_order": entry.get("order"),
                "query_text": entry.get("query_text"),
                "number_of_links": len(old_references),
                "old_reference_list": old_references,
            }
        )

    chunker = get_semantic_chunker()
    narasi_chunks: List[Document] = []
    for index, entry in enumerate(penetapan_hyperlink):
        query_text = entry.get("query_text") or ""
        if not query_text.strip():
            continue
        doc = Document(
            page_content=query_text,
            metadata={
                "heading": entry.get("heading"),
                "order": index,
                "original_order": entry.get("original_order"),
                "number_of_links": entry.get("number_of_links"),
                "old_reference_list": entry.get("old_reference_list") or [],
            },
        )
        chunks = chunker.split_documents([doc])
        for chunk_index, chunk in enumerate(chunks):
            chunk.metadata["order"] = chunk.metadata.get("order", index)
            chunk.metadata["order_heading"] = chunk_index
            chunk.metadata.setdefault("heading", entry.get("heading"))
            chunk.metadata.setdefault("original_order", entry.get("original_order"))
            chunk.metadata.setdefault("old_reference_list", entry.get("old_reference_list") or [])
            narasi_chunks.append(chunk)

    narasi_chunks.sort(key=lambda doc: (doc.metadata.get("order", 0), doc.metadata.get("order_heading", 0)))
    if not narasi_chunks:
        raise HTTPException(status_code=404, detail="Pelaksanaan chunking produced no data")

    if not section_collections:
        raise HTTPException(status_code=422, detail="No section collections configured for pelaksanaan retrieval")

    sorted_section_keys = sorted(section_collections.keys())
    active_key = sorted_section_keys[0]
    reference_documents_vectorstore = _build_vectorstore(section_collections[active_key][0])
    new_reference_vectorstore = _build_vectorstore(section_collections[active_key][1])

    title_locations: List[dict] = []
    found_titles: set[str] = set()
    for index, chunk in enumerate(narasi_chunks):
        if index in section_collections and index != active_key:
            active_key = index
            ref_collection, new_collection = section_collections[index]
            reference_documents_vectorstore = _build_vectorstore(ref_collection)
            new_reference_vectorstore = _build_vectorstore(new_collection)

        query_text = (chunk.page_content or "").strip()
        if not query_text:
            continue

        try:
            retrieved_chunks_with_score = reference_documents_vectorstore.similarity_search_with_score(
                query=query_text,
                k=reference_top_k,
            )
        except Exception as exc:  # pragma: no cover - dependent on external vector store
            logger.warning("Pelaksanaan reference retrieval failed at chunk %s: %s", index, exc)
            continue

        processed_retrieval_results: List[dict] = []
        for doc, score in retrieved_chunks_with_score:
            try:
                nested_results_raw = new_reference_vectorstore.similarity_search_with_score(
                    query=doc.page_content,
                    k=nested_top_k,
                )
            except Exception as exc:  # pragma: no cover - dependent on external vector store
                logger.warning("Pelaksanaan nested retrieval failed at chunk %s: %s", index, exc)
                nested_results_raw = []

            processed_nested_results: List[dict] = []
            for nested_doc, nested_score in nested_results_raw:
                nested_meta = nested_doc.metadata or {}
                dl_meta = nested_meta.get("dl_meta") or {}
                origin = dl_meta.get("origin") if isinstance(dl_meta, dict) else {}
                filename = None
                if isinstance(origin, dict):
                    filename = origin.get("filename")
                filename = filename or nested_meta.get("source") or nested_meta.get("document_id")
                headings = None
                if isinstance(dl_meta, dict):
                    headings = dl_meta.get("headings")
                headings = headings or nested_meta.get("headings")
                processed_nested_results.append(
                    {
                        "page_content": nested_doc.page_content,
                        "filename": filename,
                        "headings": headings,
                        "score": nested_score,
                    }
                )

            doc_meta = doc.metadata or {}
            dl_meta = doc_meta.get("dl_meta") or {}
            origin = dl_meta.get("origin") if isinstance(dl_meta, dict) else {}
            ref_filename = None
            if isinstance(origin, dict):
                ref_filename = origin.get("filename")
            ref_filename = ref_filename or doc_meta.get("source") or doc_meta.get("document_id")
            ref_headings = None
            if isinstance(dl_meta, dict):
                ref_headings = dl_meta.get("headings")
            ref_headings = ref_headings or doc_meta.get("headings")

            processed_retrieval_results.append(
                {
                    "page_content": doc.page_content,
                    "filename": ref_filename,
                    "headings": ref_headings,
                    "score": score,
                    "nested_search_results": processed_nested_results,
                }
            )

        reference_list = chunk.metadata.get("old_reference_list") or []
        for reference in reference_list:
            if isinstance(reference, dict):
                title = reference.get("page_content/title") or reference.get("title")
            else:
                title = str(reference)
            if not title or title in found_titles:
                continue
            if title.lower() not in query_text.lower():
                continue

            title_locations.append(
                {
                    "title": title,
                    "found_in_chunk": {
                        "heading": chunk.metadata.get("heading"),
                        "order": chunk.metadata.get("order"),
                        "order_heading": chunk.metadata.get("order_heading"),
                        "original_order": chunk.metadata.get("original_order"),
                    },
                    "chunk_text": query_text,
                    "retrieval_search_result": processed_retrieval_results,
                }
            )
            found_titles.add(title)

    grouped_data: Dict[int, List[dict]] = {}
    for item in title_locations:
        order_value = item.get("found_in_chunk", {}).get("order")
        if order_value is None:
            continue
        grouped_data.setdefault(order_value, []).append(item)

    final_result: List[dict] = []
    total_reference_suggestions = 0
    for order_value in sorted(grouped_data.keys()):
        items = grouped_data[order_value]
        heading = ""
        past_narrative = ""
        new_references: List[dict] = []
        seen_contents: set[str] = set()

        for item in items:
            chunk_heading = item.get("found_in_chunk", {}).get("heading")
            if chunk_heading and not heading:
                heading = chunk_heading
            candidate_content = _extract_nested_reference_content(item.get("retrieval_search_result") or [])
            if candidate_content and candidate_content not in seen_contents:
                new_references.append({"content": candidate_content})
                seen_contents.add(candidate_content)
            if not past_narrative and chunk_heading and chunk_heading in heading_to_query_map:
                past_narrative = heading_to_query_map[chunk_heading]

        if not past_narrative and heading in heading_to_query_map:
            past_narrative = heading_to_query_map[heading]

        if new_references:
            total_reference_suggestions += len(new_references)
            final_result.append(
                {
                    "order": order_value,
                    "heading": heading,
                    "past_narrative": past_narrative,
                    "new_references": new_references,
                }
            )

    payload = {
        "summary": f"Generated {len(final_result)} pelaksanaan sections with {total_reference_suggestions} reference suggestions.",
        "results": final_result,
    }
    if include_debug:
        payload["debug"] = {
            "title_matches": len(title_locations),
            "chunks_processed": len(narasi_chunks),
        }

    section_meta = {
        str(index): {"reference": ref, "new_reference": new}
        for index, (ref, new) in section_collections.items()
    }

    meta = {
        "document_collection": document_collection,
        "hyperlink_collection": hyperlink_collection if hyperlink_points else None,
        "allowed_orders": sorted(allowed_orders),
        "section_collections": section_meta,
        "penetapan_records": len(penetapan_entries),
        "hyperlink_records": len(hyperlink_points),
        "chunks_processed": len(narasi_chunks),
        "title_matches": len(title_locations),
        "chunks_returned": len(final_result),
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
    elif normalized_type == "pelaksanaan":
        payload, payload_meta = build_pelaksanaan_output(normalized_uuid, request_metadata)
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
