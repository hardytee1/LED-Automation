import logging
import os
import shutil
import tempfile
import uuid
from pathlib import Path
from typing import Iterable, List
from zipfile import BadZipFile, ZipFile

import httpx
from dotenv import load_dotenv
from fastapi import BackgroundTasks, FastAPI, HTTPException
from langchain_docling import DoclingLoader
from langchain_core.documents import Document
from langchain_text_splitters import RecursiveCharacterTextSplitter
from pydantic import BaseModel
from langchain_community.vectorstores import Qdrant
from qdrant_client import QdrantClient
from qdrant_client.http import exceptions as qdrant_exceptions
from qdrant_client.http import models as qdrant_models
from langchain_experimental.text_splitter import SemanticChunker
from langchain_huggingface import HuggingFaceEmbeddings
from sentence_transformers import SentenceTransformer

load_dotenv()

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("rag-api")

app = FastAPI(title="LED Automation RAG API")

SUPPORTED_EXTENSIONS = {".pdf", ".txt", ".md"}

EMBEDDING_MODEL_NAME = os.getenv("EMBEDDING_MODEL", "all-MiniLM-L6-v2")
QDRANT_URL = os.getenv("QDRANT_URL")
QDRANT_API_KEY = os.getenv("QDRANT_API_KEY")
QDRANT_COLLECTION = os.getenv("QDRANT_COLLECTION", "led_reference_chunks")
QDRANT_DISTANCE = os.getenv("QDRANT_DISTANCE", "COSINE").upper()
BATCH_SIZE = int(os.getenv("EMBED_BATCH_SIZE", "32"))
CHUNK_SIZE = int(os.getenv("CHUNK_SIZE", "1000"))
CHUNK_OVERLAP = int(os.getenv("CHUNK_OVERLAP", "200"))
STATUS_WEBHOOK = os.getenv("STATUS_WEBHOOK_URL")
STATUS_WEBHOOK_TOKEN = os.getenv("STATUS_WEBHOOK_TOKEN")

if not QDRANT_URL or not QDRANT_API_KEY:
    raise RuntimeError("QDRANT_URL and QDRANT_API_KEY must be set")

embedding_model_name = "denaya/indosbert-large"
embedding_model = HuggingFaceEmbeddings(model_name=embedding_model_name)
semantic_chunker = SemanticChunker(embedding_model, breakpoint_threshold_type="percentile")
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


def discover_documents(root: Path) -> List[Path]:
    return [path for path in root.rglob("*") if path.is_file() and path.suffix.lower() in SUPPORTED_EXTENSIONS]


def chunk_pdf(path: Path) -> List[Document]:
    loader = DoclingLoader(file_path=str(path))
    docs = loader.load()
    for doc in docs:
        doc.metadata = {**doc.metadata, "source": str(path)}
    return docs


def chunk_text(path: Path, splitter: RecursiveCharacterTextSplitter) -> List[Document]:
    try:
        content = path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        content = path.read_text(encoding="latin-1", errors="ignore")
    chunks = splitter.split_text(content)
    return [Document(page_content=chunk, metadata={"source": str(path)}) for chunk in chunks]


def build_chunks(documents: Iterable[Path]) -> List[Document]:
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=CHUNK_SIZE,
        chunk_overlap=CHUNK_OVERLAP,
        length_function=len,
    )
    all_docs: List[Document] = []
    for doc_path in documents:
        try:
            if doc_path.suffix.lower() == ".pdf":
                parts = chunk_pdf(doc_path)
            else:
                parts = chunk_text(doc_path, splitter)
            all_docs.extend(parts)
            logger.info("Chunked %s into %s segments", doc_path.name, len(parts))
        except Exception as exc:  # pylint: disable=broad-except
            logger.error("Failed to chunk %s: %s", doc_path, exc)
    return all_docs


def embed_chunks(docs: List[Document]) -> List[List[float]]:
    texts = [doc.page_content for doc in docs if doc.page_content.strip()]
    if not texts:
        return []
    embeddings = embedding_model.encode(
        texts,
        batch_size=BATCH_SIZE,
        show_progress_bar=False,
        convert_to_numpy=True,
    )
    return embeddings.tolist()


def upsert_chunks(docs: List[Document], vectors: List[List[float]], batch_id: int, report_id: int) -> None:
    if not docs or not vectors:
        logger.warning("No documents or vectors to upsert for batch %s", batch_id)
        return
    payloads = []
    for doc in docs:
        payloads.append(
            {
                "batch_id": batch_id,
                "report_id": report_id,
                "source": doc.metadata.get("source"),
                "text": doc.page_content,
            }
        )
    points = [
        qdrant_models.PointStruct(id=uuid.uuid4().int >> 64, vector=vector, payload=payload)
        for vector, payload in zip(vectors, payloads)
    ]
    qdrant_client.upsert(collection_name=QDRANT_COLLECTION, points=points)
    logger.info("Upserted %s chunks for batch %s", len(points), batch_id)


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
        documents = discover_documents(working_dir)
        if not documents:
            raise RuntimeError("No supported documents found in the archive")
        chunks = build_chunks(documents)
        if not chunks:
            raise RuntimeError("Failed to create chunks from documents")
        vectors = embed_chunks(chunks)
        if not vectors:
            raise RuntimeError("Embedding model returned no vectors")
        upsert_chunks(chunks, vectors, batch_id, report_id)
        notify_status(batch_id, "completed", {"chunks": len(chunks)})
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
