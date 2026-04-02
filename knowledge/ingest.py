"""Ingestion pipeline: markdown files -> chunks -> Gemini embeddings -> ChromaDB.

Usage:
    python -m knowledge.ingest
"""

import os
import sys
import time
from pathlib import Path

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
load_dotenv(PROJECT_ROOT / ".env")

KNOWLEDGE_DIR = PROJECT_ROOT / "knowledge"
CHROMA_DIR = PROJECT_ROOT / "chroma_db"
COLLECTION_NAME = "fitness_knowledge"
CHUNK_SIZE = 1000
CHUNK_OVERLAP = 200

TOPIC_MAP = {
    "biomechanics.md": "biomechanics",
    "contraindications.md": "contraindications",
    "programming.md": "programming",
    "injuries.md": "injuries",
    "nutrition_science.md": "nutrition",
    "special_populations.md": "special_populations",
}


def split_markdown(text: str, chunk_size: int = CHUNK_SIZE, overlap: int = CHUNK_OVERLAP) -> list[str]:
    """Split markdown text into overlapping chunks, preferring heading boundaries."""
    separators = ["\n## ", "\n### ", "\n---\n", "\n\n", "\n"]

    def _split(text: str, seps: list[str]) -> list[str]:
        if len(text) <= chunk_size:
            return [text] if text.strip() else []

        sep = seps[0]
        rest_seps = seps[1:] if len(seps) > 1 else seps

        parts = text.split(sep)
        if len(parts) == 1:
            if rest_seps != seps:
                return _split(text, rest_seps)
            return [text[i:i + chunk_size] for i in range(0, len(text), chunk_size - overlap)
                    if text[i:i + chunk_size].strip()]

        chunks: list[str] = []
        current = ""
        for part in parts:
            candidate = (current + sep + part) if current else part
            if len(candidate) > chunk_size and current.strip():
                chunks.append(current.strip())
                tail = current[-(overlap):] if len(current) > overlap else current
                current = tail + sep + part
            else:
                current = candidate

        if current.strip():
            chunks.append(current.strip())

        return chunks

    return _split(text, separators)


def load_documents() -> list[dict]:
    """Load and chunk all markdown files from the knowledge directory."""
    documents: list[dict] = []
    md_files = sorted(KNOWLEDGE_DIR.glob("*.md"))

    if not md_files:
        print("No .md files found in knowledge/")
        return documents

    for fpath in md_files:
        topic = TOPIC_MAP.get(fpath.name, fpath.stem)
        text = fpath.read_text(encoding="utf-8")
        chunks = split_markdown(text)

        for i, chunk in enumerate(chunks):
            documents.append({
                "id": f"{fpath.stem}_{i:03d}",
                "text": chunk,
                "metadata": {
                    "topic": topic,
                    "source": fpath.name,
                    "chunk_index": i,
                },
            })

        print(f"  {fpath.name}: {len(chunks)} chunks")

    return documents


def embed_texts(texts: list[str], api_key: str) -> list[list[float]]:
    """Generate embeddings via Gemini text-embedding-004."""
    from google import genai

    client = genai.Client(api_key=api_key)
    embeddings: list[list[float]] = []

    batch_size = 20
    for i in range(0, len(texts), batch_size):
        batch = texts[i:i + batch_size]
        for text in batch:
            result = client.models.embed_content(
                model="models/gemini-embedding-001",
                contents=text,
            )
            embeddings.append(result.embeddings[0].values)

        if i + batch_size < len(texts):
            time.sleep(0.5)

    return embeddings


def ingest():
    """Main ingestion: read markdown -> chunk -> embed -> store in ChromaDB."""
    import chromadb

    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        print("Error: GEMINI_API_KEY not set in .env")
        sys.exit(1)

    print("Loading and chunking knowledge base...")
    documents = load_documents()

    if not documents:
        print("No documents to ingest.")
        return

    print(f"\nTotal: {len(documents)} chunks")

    print("\nGenerating embeddings via Gemini text-embedding-004...")
    texts = [doc["text"] for doc in documents]
    embeddings = embed_texts(texts, api_key)
    print(f"Generated {len(embeddings)} embeddings (dim={len(embeddings[0])})")

    print(f"\nStoring in ChromaDB at {CHROMA_DIR}...")
    CHROMA_DIR.mkdir(exist_ok=True)
    client = chromadb.PersistentClient(path=str(CHROMA_DIR))

    try:
        client.delete_collection(COLLECTION_NAME)
        print(f"  Deleted existing collection '{COLLECTION_NAME}'")
    except Exception:
        pass

    collection = client.create_collection(
        name=COLLECTION_NAME,
        metadata={"hnsw:space": "cosine"},
    )

    collection.add(
        ids=[doc["id"] for doc in documents],
        documents=texts,
        embeddings=embeddings,
        metadatas=[doc["metadata"] for doc in documents],
    )

    print(f"  Stored {collection.count()} documents in collection '{COLLECTION_NAME}'")
    print("\nDone! Knowledge base is ready.")


if __name__ == "__main__":
    ingest()
