import logging
import os
import shutil
import tempfile
from pathlib import Path
from typing import List
from zipfile import BadZipFile, ZipFile

import httpx
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from langchain_docling import DoclingLoader
from langchain_core.documents import Document
from langchain_community.vectorstores import Qdrant
from langchain_huggingface import HuggingFaceEmbeddings
from pydantic import BaseModel
from qdrant_client import QdrantClient
from qdrant_client.http import models as qdrant_models
from docling_core.types import ExportType
from docling.chunking import HybridChunker

load_dotenv()

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("gpu-comp")

app = FastAPI(title="GPU Embedding Service")

EMBEDDING_MODEL_NAME = os.getenv("EMBEDDING_MODEL", "denaya/indosbert-large")
QDRANT_URL = os.getenv("QDRANT_URL")
QDRANT_API_KEY = os.getenv("QDRANT_API_KEY")
QDRANT_COLLECTION = os.getenv("QDRANT_COLLECTION", "cova_led_reference_chunks")
QDRANT_DISTANCE = os.getenv("QDRANT_DISTANCE", "COSINE").upper()

if not QDRANT_URL or not QDRANT_API_KEY:
    raise RuntimeError("QDRANT_URL and QDRANT_API_KEY must be set")

embedding_model = HuggingFaceEmbeddings(model_name=EMBEDDING_MODEL_NAME)
qdrant_client = QdrantClient(url=QDRANT_URL, api_key=QDRANT_API_KEY)

VECTOR_SIZE = len(embedding_model.embed_query("dimension probe"))


def ensure_collection() -> None:
    try:
        qdrant_client.get_collection(QDRANT_COLLECTION)
    except Exception:
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
        logger.warning("Failed cleanup %s: %s", path, exc)


def extract_zip(zip_path: Path) -> Path:
    workdir = Path(tempfile.mkdtemp(prefix="gpu-comp-"))
    try:
        with ZipFile(zip_path, "r") as archive:
            archive.extractall(workdir)
    except BadZipFile as exc:
        cleanup_directory(workdir)
        raise RuntimeError(f"Invalid ZIP archive: {zip_path}") from exc
    return workdir


def load_documents(root: Path) -> List[Document]:
    documents: List[Document] = []
    for file_path in root.rglob("*.pdf"):
        loader = DoclingLoader(
            file_path=str(file_path),
            export_type=ExportType.DOC_CHUNKS,
            chunker=HybridChunker(tokenizer=EMBEDDING_MODEL_NAME),
        )
        loaded = loader.load()
        for doc in loaded:
            doc.metadata = {**doc.metadata, "source": str(file_path)}
        documents.extend(loaded)
    return documents


class IngestRequest(BaseModel):
    file_path: str
    batch_id: int
    report_id: int


@app.post("/ingest")
async def ingest(request: IngestRequest):
    archive_path = Path(request.file_path)
    if not archive_path.exists():
        raise HTTPException(status_code=404, detail="File not found")

    ensure_collection()
    workdir = extract_zip(archive_path)
    try:
        documents = load_documents(workdir)
        if not documents:
            raise HTTPException(status_code=400, detail="No PDF documents found")

        vectorstore = Qdrant(
            client=qdrant_client,
            collection_name=QDRANT_COLLECTION,
            embeddings=embedding_model,
        )
        vectorstore.add_documents(documents)
        return {"chunks": len(documents)}
    finally:
        cleanup_directory(workdir)


@app.get("/health")
async def health():
    return {"status": "ok"}
