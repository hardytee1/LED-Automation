import logging
import os
import shutil
import tempfile
from pathlib import Path
from typing import List
from uuid import UUID
from zipfile import BadZipFile, ZipFile

import httpx
from dotenv import load_dotenv
from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from langchain_docling import DoclingLoader
from langchain_core.documents import Document
from langchain_community.vectorstores import Qdrant
from langchain_huggingface import HuggingFaceEmbeddings
from qdrant_client import QdrantClient
from qdrant_client.http import models as qdrant_models
from langchain_docling.loader import ExportType
from docling.chunking import HybridChunker

load_dotenv()

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("gpu-comp")

app = FastAPI(title="GPU Embedding Service")

EMBEDDING_MODEL_NAME = os.getenv("EMBEDDING_MODEL", "denaya/indosbert-large")
QDRANT_URL = os.getenv("QDRANT_URL")
QDRANT_API_KEY = os.getenv("QDRANT_API_KEY")
QDRANT_DISTANCE = os.getenv("QDRANT_DISTANCE", "COSINE").upper()

if not QDRANT_URL:
    raise RuntimeError("QDRANT_URL must be set")

if not QDRANT_API_KEY:
    logger.warning("QDRANT_API_KEY is not set; assuming local Qdrant without authentication")

embedding_model = HuggingFaceEmbeddings(model_name=EMBEDDING_MODEL_NAME)
qdrant_client = QdrantClient(url=QDRANT_URL, api_key=QDRANT_API_KEY or None)

VECTOR_SIZE = len(embedding_model.embed_query("dimension probe"))


def ensure_collection(collection_name: str) -> None:
    try:
        qdrant_client.get_collection(collection_name)
    except Exception:
        qdrant_client.recreate_collection(
            collection_name=collection_name,
            vectors_config=qdrant_models.VectorParams(
                size=VECTOR_SIZE,
                distance=getattr(qdrant_models.Distance, QDRANT_DISTANCE, qdrant_models.Distance.COSINE),
            ),
        )


def cleanup_directory(path: Path) -> None:
    try:
        shutil.rmtree(path)
    except OSError as exc:
        logger.warning("Failed cleanup %s: %s", path, exc)


def cleanup_file(path: Path) -> None:
    if not path.exists():
        return
    try:
        path.unlink()
    except OSError as exc:
        logger.warning("Failed file cleanup %s: %s", path, exc)


def extract_zip(zip_path: Path) -> Path:
    workdir = Path(tempfile.mkdtemp(prefix="gpu-comp-"))
    try:
        with ZipFile(zip_path, "r") as archive:
            archive.extractall(workdir)
    except BadZipFile as exc:
        cleanup_directory(workdir)
        raise RuntimeError(f"Invalid ZIP archive: {zip_path}") from exc
    return workdir


SUPPORTED_DOC_EXTENSIONS = {".pdf", ".xlsx", ".csv", ".csx", ".pptx"}


def load_documents(root: Path) -> List[Document]:
    documents: List[Document] = []
    document_paths = [
        path
        for path in root.rglob("*")
        if path.is_file() and path.suffix.lower() in SUPPORTED_DOC_EXTENSIONS
    ]

    if not document_paths:
        logger.warning("No supported documents found in %s", root)
        return documents

    for file_path in document_paths:
        logger.info("Processing reference file: %s", file_path)
        try:
            loader = DoclingLoader(
                file_path=str(file_path),
                export_type=ExportType.DOC_CHUNKS,
                chunker=HybridChunker(tokenizer=EMBEDDING_MODEL_NAME),
            )
            loaded = loader.load()
            logger.info("  - Created %d hybrid chunks.", len(loaded))
        except Exception as exc:
            logger.exception("  - ERROR processing file %s: %s", file_path, exc)
            continue

        for doc in loaded:
            doc.metadata = {**doc.metadata, "source": str(file_path)}
        documents.extend(loaded)

    logger.info("Total chunks generated: %d", len(documents))
    return documents


async def persist_upload(upload: UploadFile) -> Path:
    suffix = Path(upload.filename or "reference-batch.zip").suffix or ".zip"
    fd, temp_path = tempfile.mkstemp(prefix="gpu-upload-", suffix=suffix)
    path = Path(temp_path)
    with os.fdopen(fd, "wb") as buffer:
        while True:
            chunk = await upload.read(1024 * 1024)
            if not chunk:
                break
            buffer.write(chunk)
    await upload.close()
    return path


@app.post("/ingest")
async def ingest(
    batch_id: int = Form(...),
    report_uuid: str = Form(...),
    archive: UploadFile = File(...),
):
    try:
        normalized_uuid = str(UUID(report_uuid))
    except (ValueError, TypeError) as exc:
        raise HTTPException(status_code=422, detail="Invalid report_uuid") from exc

    ensure_collection(normalized_uuid)
    archive_path = await persist_upload(archive)
    workdir: Path | None = None
    try:
        workdir = extract_zip(archive_path)
        documents = load_documents(workdir)
        if not documents:
            raise HTTPException(status_code=400, detail="No supported documents found")

        vectorstore = Qdrant(
            client=qdrant_client,
            collection_name=normalized_uuid,
            embeddings=embedding_model,
        )
        vectorstore.add_documents(documents)
        return {"chunks": len(documents), "collection": normalized_uuid}
    finally:
        if workdir:
            cleanup_directory(workdir)
        cleanup_file(archive_path)


@app.get("/health")
async def health():
    return {"status": "ok"}
