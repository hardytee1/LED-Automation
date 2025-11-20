import logging
import os
import shutil
import tempfile
import uuid
from pathlib import Path
from typing import List
from zipfile import BadZipFile, ZipFile

import httpx
from dotenv import load_dotenv
from fastapi import BackgroundTasks, FastAPI, HTTPException
from langchain_docling import DoclingLoader
from langchain_core.documents import Document
from langchain_community.vectorstores import Qdrant
from pydantic import BaseModel
from qdrant_client import QdrantClient
from qdrant_client.http import exceptions as qdrant_exceptions
from qdrant_client.http import models as qdrant_models
from langchain_huggingface import HuggingFaceEmbeddings
from sentence_transformers import SentenceTransformer
from docling_core.types import ExportType
from docling.chunking import HybridChunker

load_dotenv()

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("rag-api")

app = FastAPI(title="LED Automation RAG API")

EMBEDDING_MODEL_NAME = os.getenv("EMBEDDING_MODEL", "all-MiniLM-L6-v2")
QDRANT_URL = os.getenv("QDRANT_URL")
QDRANT_API_KEY = os.getenv("QDRANT_API_KEY")
QDRANT_COLLECTION = os.getenv("QDRANT_COLLECTION", "led_reference_chunks")
QDRANT_DISTANCE = os.getenv("QDRANT_DISTANCE", "COSINE").upper()
STATUS_WEBHOOK = os.getenv("STATUS_WEBHOOK_URL")
STATUS_WEBHOOK_TOKEN = os.getenv("STATUS_WEBHOOK_TOKEN")

if not QDRANT_URL or not QDRANT_API_KEY:
    raise RuntimeError("QDRANT_URL and QDRANT_API_KEY must be set")

embedding_model_name = "denaya/indosbert-large"
embedding_model = HuggingFaceEmbeddings(model_name=embedding_model_name)
qdrant_client = QdrantClient(url=QDRANT_URL, api_key=QDRANT_API_KEY)

try:
    VECTOR_SIZE = len(embedding_model.embed_query("dimension probe"))
except Exception as exc:  # pylint: disable=broad-except
    raise RuntimeError("Failed to determine embedding vector size") from exc


def ensure_collection() -> None:
    try:
        qdrant_client.get_collection(QDRANT_COLLECTION)
        logger.info("Using existing Qdrant collection '%s'", QDRANT_COLLECTION)
    except qdrant_exceptions.UnexpectedResponse:
        logger.info("Creating Qdrant collection '%s' with vector size %s", QDRANT_COLLECTION, VECTOR_SIZE)
        qdrant_client.recreate_collection(
            collection_name=QDRANT_COLLECTION,
            vectors_config=qdrant_models.VectorParams(
                size=VECTOR_SIZE,
                distance=getattr(qdrant_models.Distance, QDRANT_DISTANCE, qdrant_models.Distance.COSINE),
            ),
        )


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
    report_id: int


def process_reference_batch(file_path: str, batch_id: int, report_id: int) -> None:
    ensure_collection()
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
            collection_name=QDRANT_COLLECTION,
            embeddings=embedding_model,
        )
        vectorstore.add_documents(documents)
        notify_status(batch_id, "completed", {"chunks": len(documents)})
    except Exception as exc:  # pylint: disable=broad-except
        logger.exception("Batch %s failed", batch_id)
        notify_status(batch_id, "failed", {"error": str(exc)})
    finally:
        cleanup_directory(working_dir)


@app.post("/ingest")
async def ingest_batch(request: IngestRequest, background_tasks: BackgroundTasks):
    archive_path = Path(request.file_path)
    if not archive_path.exists():
        raise HTTPException(status_code=404, detail=f"File not found at path: {archive_path}")

    background_tasks.add_task(process_reference_batch, str(archive_path), request.batch_id, request.report_id)
    return {"status": "processing_started", "file_path": str(archive_path)}


@app.get("/health")
async def health_check():
    return {"status": "ok"}
