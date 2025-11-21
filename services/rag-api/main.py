import json
import logging
import os
import shutil
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Tuple
from uuid import UUID
from zipfile import BadZipFile, ZipFile

import httpx
from dotenv import load_dotenv
from fastapi import BackgroundTasks, FastAPI, HTTPException, Header
from langchain_docling import DoclingLoader
from langchain_core.documents import Document
from langchain_community.vectorstores import Qdrant
from pydantic import BaseModel
from qdrant_client import QdrantClient
from qdrant_client.http import exceptions as qdrant_exceptions
from qdrant_client.http import models as qdrant_models
from langchain_huggingface import HuggingFaceEmbeddings
from docling_core.types import ExportType
from docling.chunking import HybridChunker

load_dotenv()

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("rag-api")

app = FastAPI(title="LED Automation RAG API")
EMBEDDING_MODEL_NAME = os.getenv("EMBEDDING_MODEL", "all-MiniLM-L6-v2")
QDRANT_URL = os.getenv("QDRANT_URL")
QDRANT_API_KEY = os.getenv("QDRANT_API_KEY")
QDRANT_DISTANCE = os.getenv("QDRANT_DISTANCE", "COSINE").upper()
STATUS_WEBHOOK = os.getenv("STATUS_WEBHOOK_URL")
STATUS_WEBHOOK_TOKEN = os.getenv("STATUS_WEBHOOK_TOKEN")
AUTOMATION_SERVICE_TOKEN = os.getenv("AUTOMATION_SERVICE_TOKEN")
OUTPUT_ARTIFACT_DIR = Path(os.getenv("REPORT_OUTPUT_ARTIFACT_DIR", Path(__file__).parent / "artifacts"))
OUTPUT_RESULT_LIMIT = int(os.getenv("REPORT_OUTPUT_RESULT_LIMIT", "8"))
SUPPORTED_OUTPUT_TYPES = {"penetapan", "pelaksanaan"}

if not QDRANT_URL or not QDRANT_API_KEY:
    raise RuntimeError("QDRANT_URL and QDRANT_API_KEY must be set")

embedding_model_name = "denaya/indosbert-large"
embedding_model = HuggingFaceEmbeddings(model_name=embedding_model_name)
qdrant_client = QdrantClient(url=QDRANT_URL, api_key=QDRANT_API_KEY)

try:
    VECTOR_SIZE = len(embedding_model.embed_query("dimension probe"))
except Exception as exc:  # pylint: disable=broad-except
    raise RuntimeError("Failed to determine embedding vector size") from exc


def ensure_collection(collection_name: str) -> None:
    try:
        qdrant_client.get_collection(collection_name)
        logger.info("Using existing Qdrant collection '%s'", collection_name)
    except qdrant_exceptions.UnexpectedResponse:
        logger.info("Creating Qdrant collection '%s' with vector size %s", collection_name, VECTOR_SIZE)
        qdrant_client.recreate_collection(
            collection_name=collection_name,
            vectors_config=qdrant_models.VectorParams(
                size=VECTOR_SIZE,
                distance=getattr(qdrant_models.Distance, QDRANT_DISTANCE, qdrant_models.Distance.COSINE),
            ),
        )


def collection_exists(collection_name: str) -> bool:
    try:
        qdrant_client.get_collection(collection_name)
        return True
    except qdrant_exceptions.UnexpectedResponse:
        return False


def ensure_artifact_directory() -> None:
    OUTPUT_ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)


def cleanup_directory(path: Path) -> None:
    try:
        shutil.rmtree(path)
    except OSError as exc:
        logger.warning("Failed to clean temp directory %s: %s", path, exc)


def extract_zip(zip_path: Path) -> Path:
    workdir = Path(tempfile.mkdtemp(prefix="rag-batch-"))
    try:
        with ZipFile(zip_path, "r") as archive:
            archive.extractall(workdir)
    except BadZipFile as exc:
        cleanup_directory(workdir)
        raise RuntimeError(f"Invalid ZIP archive: {zip_path}") from exc
    return workdir


def load_reference_documents(root: Path) -> List[Document]:
    documents: List[Document] = []
    for file_path in root.rglob("*"):
        if not file_path.is_file() or file_path.suffix.lower() != ".pdf":
            continue
        try:
            loader = DoclingLoader(
                file_path=str(file_path),
                export_type=ExportType.DOC_CHUNKS,
                chunker=HybridChunker(tokenizer=embedding_model_name),
            )
            loaded = loader.load()
            for doc in loaded:
                doc.metadata = {**doc.metadata, "source": str(file_path)}
            documents.extend(loaded)
            logger.info("Processed %s -> %s chunks", file_path.name, len(loaded))
        except Exception as exc:  # pylint: disable=broad-except
            logger.error("Failed to process %s: %s", file_path, exc)
    return documents


def notify_status(batch_id: int, status: str, details: dict | None = None) -> None:
    if not STATUS_WEBHOOK:
        return
    payload = {"batch_id": batch_id, "status": status, "details": details or {}}
    headers = {"Authorization": f"Bearer {STATUS_WEBHOOK_TOKEN}"} if STATUS_WEBHOOK_TOKEN else {}
    try:
        response = httpx.post(STATUS_WEBHOOK, json=payload, headers=headers, timeout=10)
        response.raise_for_status()
    except Exception as exc:  # pylint: disable=broad-except
        logger.error("Failed to notify webhook: %s", exc)


class IngestRequest(BaseModel):
    file_path: str
    batch_id: int
    report_uuid: str


class OutputRequest(BaseModel):
    job_key: str
    report_id: int
    user_id: int
    metadata: dict | None = None


def process_reference_batch(file_path: str, batch_id: int, report_uuid: str) -> None:
    ensure_collection(report_uuid)
    archive_path = Path(file_path)
    if not archive_path.exists():
        raise RuntimeError(f"File not found: {file_path}")

    working_dir = extract_zip(archive_path)
    logger.info("Extracted ZIP to %s", working_dir)
    try:
        documents = load_reference_documents(working_dir)
        if not documents:
            raise RuntimeError("No PDF documents found in the archive")

        vectorstore = Qdrant(
            client=qdrant_client,
            collection_name=report_uuid,
            embeddings=embedding_model,
        )
        vectorstore.add_documents(documents)
        notify_status(batch_id, "completed", {"chunks": len(documents), "collection": report_uuid})
    except Exception as exc:  # pylint: disable=broad-except
        logger.exception("Batch %s failed", batch_id)
        notify_status(batch_id, "failed", {"error": str(exc), "collection": report_uuid})
    finally:
        cleanup_directory(working_dir)


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


def write_artifact(report_uuid: str, output_type: str, job_key: str, payload: dict) -> str:
    ensure_artifact_directory()
    filename = f"{report_uuid}-{output_type}-{job_key}.json"
    artifact_path = OUTPUT_ARTIFACT_DIR / filename
    artifact_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return str(artifact_path)


@app.post("/ingest")
async def ingest_batch(request: IngestRequest, background_tasks: BackgroundTasks):
    archive_path = Path(request.file_path)
    if not archive_path.exists():
        raise HTTPException(status_code=404, detail=f"File not found at path: {archive_path}")

    try:
        normalized_uuid = str(UUID(request.report_uuid))
    except (ValueError, TypeError) as exc:
        raise HTTPException(status_code=422, detail="Invalid report_uuid") from exc

    background_tasks.add_task(process_reference_batch, str(archive_path), request.batch_id, normalized_uuid)
    return {"status": "processing_started", "file_path": str(archive_path)}


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

    if not collection_exists(normalized_uuid):
        raise HTTPException(status_code=404, detail="No references ingested for this report")

    records, total_chunks = fetch_reference_chunks(normalized_uuid, OUTPUT_RESULT_LIMIT)
    if not records:
        raise HTTPException(status_code=404, detail="No chunks stored for this report")

    chunks = serialize_chunks(records)
    generated_at = datetime.now(timezone.utc).isoformat()
    payload = {
        "summary": f"Retrieved {len(chunks)} reference chunks for {normalized_type} review.",
        "results": chunks,
    }

    meta = {
        "generated_at": generated_at,
        "job_key": request.job_key,
        "report_id": request.report_id,
        "user_id": request.user_id,
        "output_type": normalized_type,
        "chunks_returned": len(chunks),
        "total_chunks": total_chunks,
    }

    artifact_path = write_artifact(normalized_uuid, normalized_type, request.job_key, {
        "payload": payload,
        "meta": meta,
    })

    return {
        "status": "completed",
        "payload": payload,
        "artifact_path": artifact_path,
        "meta": meta,
    }


@app.get("/health")
async def health_check():
    return {"status": "ok"}
