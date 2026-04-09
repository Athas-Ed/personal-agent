from __future__ import annotations

from dataclasses import dataclass
from typing import List, Tuple

from langchain_core.documents import Document

from .config import Settings
from .llm import build_chat_llm
from .vectorstore import get_vectorstore


@dataclass(frozen=True)
class RAGResult:
    answer: str
    sources: List[Tuple[str, str]]


def _chat_only(settings: Settings, question: str) -> RAGResult:
    llm = build_chat_llm(settings)
    system = "你是个人工作台助手。请用简洁、自然的中文回答用户。"
    msg = llm.invoke(
        [
            {"role": "system", "content": system},
            {"role": "user", "content": question},
        ]
    )
    return RAGResult(answer=str(msg.content), sources=[])


def answer_with_rag(settings: Settings, question: str, k: int = 4) -> RAGResult:
    # 保证“基础对话”永远可用：知识库为空或检索/embedding 失败时自动降级为纯对话。
    try:
        vs = get_vectorstore(settings)

        collection = getattr(vs, "_collection", None)
        if collection is not None:
            try:
                if int(collection.count()) == 0:
                    return _chat_only(settings, question)
            except Exception:
                pass

        retriever = vs.as_retriever(search_kwargs={"k": k})
        docs: List[Document] = retriever.invoke(question)
    except Exception:
        return _chat_only(settings, question)

    llm = build_chat_llm(settings)

    context = "\n\n".join(f"[{i+1}] {d.page_content}" for i, d in enumerate(docs)).strip()

    system = (
        "你是个人工作台助手。请基于给定的资料片段回答问题；"
        "如果资料不足以支持结论，请明确说“资料不足”，并给出你需要的补充信息。"
    )
    user = f"问题：{question}\n\n资料片段：\n{context}"

    msg = llm.invoke(
        [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ]
    )

    sources: List[Tuple[str, str]] = []
    for i, d in enumerate(docs):
        src = str(d.metadata.get("source", f"chunk_{i+1}"))
        preview = d.page_content[:240].replace("\n", " ").strip()
        sources.append((src, preview))

    return RAGResult(answer=str(msg.content), sources=sources)

