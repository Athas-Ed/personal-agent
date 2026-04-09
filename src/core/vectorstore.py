from __future__ import annotations

import os
from typing import Iterable

from langchain_chroma import Chroma
from langchain_core.documents import Document

from .config import Settings
from .llm import build_embeddings


def get_vectorstore(settings: Settings) -> Chroma:
    os.makedirs(settings.chroma_persist_dir, exist_ok=True)
    embeddings = build_embeddings(settings)
    return Chroma(
        collection_name=settings.collection_name,
        persist_directory=settings.chroma_persist_dir,
        embedding_function=embeddings,
    )


def add_documents(settings: Settings, docs: Iterable[Document]) -> int:
    vs = get_vectorstore(settings)
    ids = vs.add_documents(list(docs))
    return len(ids or [])

