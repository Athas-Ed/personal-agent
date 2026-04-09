from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from pydantic import BaseModel, Field
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_core.runnables import RunnableLambda

from src.core.config import Settings
from src.core.llm import build_chat_llm
from src.tools.fs import resolve_under, write_text


@dataclass(frozen=True)
class StudyNoteResult:
    rel_path: str
    abs_path: str
    markdown: str
    title: str
    category: str


_WIN_FORBIDDEN = re.compile(r'[<>:"/\\\\|?*]')


def _safe_filename(name: str, fallback: str = "学习笔记") -> str:
    s = (name or "").strip()
    s = _WIN_FORBIDDEN.sub("_", s)
    s = re.sub(r"\s+", " ", s).strip()
    if not s:
        s = fallback
    # Avoid trailing dots/spaces on Windows
    s = s.rstrip(". ").strip()
    if not s:
        s = fallback
    return s[:120]


def _guess_note_type(text: str) -> str:
    """
    本地快速判定（用于兜底纠偏）：
    - “是什么/定义/概念/名词解释/区别/对比”倾向名词解释
    - “怎么做/实现/配置/排错/报错/调参”倾向技术实践
    """
    t = (text or "").strip().lower()
    if not t:
        return "技术实践"

    glossary_markers = ["是什么", "是啥", "定义", "概念", "名词解释", "什么意思", "区别", "对比", "vs", "对照"]
    practice_markers = ["怎么做", "如何", "实现", "配置", "部署", "报错", "错误", "排查", "调参", "最佳实践", "代码"]

    if any(m in t for m in glossary_markers):
        return "名词解释"
    if any(m in t for m in practice_markers):
        return "技术实践"
    return "技术实践"


def _guess_topic_folder(text: str) -> str:
    """
    本地主题目录兜底（LLM 给不出来/给错时用）。
    允许多级目录。
    """
    t = (text or "").lower()
    if any(k in t for k in ["spring boot", "springboot", "spring mvc", "spring cloud", "mybatis", "jpa"]):
        return "Java后端/Spring Boot"
    if any(k in t for k in ["java", "jvm", "tomcat", "maven", "gradle"]):
        return "Java后端"
    if any(k in t for k in ["rag", "embedding", "向量", "召回", "重排", "rerank", "chunk", "分块", "prompt", "agent", "langchain", "mcp", "llm"]):
        return "大模型技术"
    if any(k in t for k in ["streamlit"]):
        return "大模型技术/Streamlit"
    return "未分类"


def _safe_path_part(part: str, fallback: str = "未分类") -> str:
    p = _safe_filename(part, fallback=fallback)
    # Avoid path traversal-ish or empty-ish parts
    p = p.replace("/", "_").replace("\\", "_").strip()
    return p or fallback


def _sanitize_folder_rel(folder: str, fallback: str = "未分类") -> str:
    """
    清洗相对文件夹路径，允许多级目录（用 / 分隔），每段做 Windows 文件名清洗。
    """
    f = (folder or "").strip().replace("\\", "/").strip("/")
    if not f:
        return fallback
    if any(x in f for x in ["..", ":", "//"]):
        return fallback
    # Reject time-based folders like YYYY/MM or YYYY/MM/DD (and common variants YYYY-MM, YYYY_MM...).
    if re.fullmatch(r"\d{4}([/_-])\d{2}(\1\d{2})?", f):
        return fallback
    parts = [p for p in f.split("/") if p.strip()]
    if not parts:
        return fallback
    return "/".join(_safe_path_part(p, fallback=fallback) for p in parts)


def _sanitize_rel_path(rel_path: str, fallback: str) -> str:
    """
    将 LLM 产出的相对路径做强约束清洗：
    - 只能是相对路径
    - 禁止 ..、盘符、协议等
    - 每一段做 Windows 文件名清洗
    """
    rp = (rel_path or "").strip().replace("\\", "/").lstrip("/")
    if not rp or not rp.endswith(".md"):
        return fallback
    if any(x in rp for x in ["..", ":", "//"]):
        return fallback
    # Reject time-based directory prefixes like YYYY/MM/... or YYYY-MM/... etc.
    if re.match(r"^\d{4}([/_-])\d{2}(\1\d{2})?/", rp):
        return fallback

    parts = [p for p in rp.split("/") if p.strip()]
    if not parts:
        return fallback
    parts2 = [_safe_path_part(p, fallback="未分类") for p in parts]
    # Ensure .md suffix stays
    if not parts2[-1].lower().endswith(".md"):
        parts2[-1] = _safe_filename(parts2[-1], fallback="学习笔记") + ".md"
    return "/".join(parts2)


def _heuristic_category(text: str) -> str:
    t = (text or "").lower()
    if any(k in t for k in ["llm", "langchain", "prompt", "embedding", "rag", "mcp", "agent", "deepseek"]):
        return "AI-LLM"
    if any(k in t for k in ["python", "java", "c++", "js", "typescript", "bug", "报错", "代码", "算法"]):
        return "编程"
    if any(k in t for k in ["菜谱", "做饭", "食谱", "健身", "减脂", "旅行", "生活"]):
        return "生活"
    return "杂项"


def _default_rel_path(title: str, note_type: str, topic_folder: str) -> str:
    """
    新的默认路径策略：
    - 名词解释：study_files/名词解释/<标题>.md
    - 技术实践：study_files/<主题文件夹>/<标题>.md（允许自动创建主题文件夹）
    """
    title2 = _safe_filename(title, fallback="学习笔记")
    if note_type == "名词解释":
        return f"名词解释/{title2}.md"
    folder = _sanitize_folder_rel(topic_folder or "未分类", fallback="未分类")
    return f"{folder}/{title2}.md"


def _build_markdown_fallback(
    title: str,
    category: str,
    items: List[Tuple[str, str]],
    start_i: int,
    end_i: int,
) -> str:
    lines: List[str] = []
    lines.append(f"# {title}")
    lines.append("")
    lines.append(f"- 分类：{category}")
    lines.append(f"- 对话区间：{start_i}–{end_i}")
    lines.append(f"- 生成时间：{datetime.now():%Y-%m-%d %H:%M}")
    lines.append("")
    lines.append("## 问答摘录")
    lines.append("")
    for i, (q, a) in enumerate(items, start=1):
        lines.append(f"### Q{i}")
        lines.append(q.strip())
        lines.append("")
        lines.append(f"### A{i}")
        lines.append(a.strip())
        lines.append("")
    lines.append("## 知识点")
    lines.append("")
    lines.append("- （待补充）")
    lines.append("")
    lines.append("## 下一步")
    lines.append("")
    lines.append("- （待补充）")
    lines.append("")
    return "\n".join(lines).strip() + "\n"


def _pair_qa(messages: List[Dict[str, str]]) -> List[Tuple[str, str]]:
    pairs: List[Tuple[str, str]] = []
    pending_q: Optional[str] = None
    for m in messages:
        role = (m.get("role") or "").strip()
        content = (m.get("content") or "").strip()
        if not content:
            continue
        if role == "user":
            pending_q = content
        elif role == "assistant":
            if pending_q is None:
                continue
            pairs.append((pending_q, content))
            pending_q = None
    return pairs


def _llm_summarize_to_md(
    settings: Settings,
    messages: List[Dict[str, str]],
    category_hint: str,
    *,
    max_chars: int = 8000,
    existing_topic_folders: Optional[List[str]] = None,
) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
    """
    尽量让模型输出结构化 JSON（仅用于内部解析，不要求用户遵守 JSON-only 协议）。
    解析失败则返回 None，调用方会走 fallback。
    """
    llm = build_chat_llm(settings)
    parts: List[str] = []
    used = 0
    for i, m in enumerate(messages):
        content = str(m.get("content", "")).strip()
        if not content:
            continue
        piece = f"[{i+1}][{m.get('role','')}] {content}"
        # 截断：避免对话过长导致延迟/超时
        remaining = max_chars - used
        if remaining <= 0:
            break
        if len(piece) > remaining:
            piece = piece[: max(0, remaining - 20)] + " …(已截断)"
        parts.append(piece)
        used += len(piece) + 2
    convo = "\n\n".join(parts)
    existing = existing_topic_folders or []
    existing_s = "、".join(existing[:30]) if existing else "（无）"

    system = (
        "你是“问答辅助学习”助理。你的任务是把一段对话整理成学习笔记，并决定保存路径。"
        "请输出严格 JSON（不要输出多余文本），字段："
        "note_type(字符串，只能是“名词解释”或“技术实践”), "
        "topic_folder(字符串，相对 study_files/ 的文件夹，不含文件名；名词解释时可为空), "
        "title(字符串), "
        "rel_path(字符串，相对 study_files/，必须以 .md 结尾), "
        "markdown(字符串，完整Markdown)。"
        "规则："
        "1) 如果用户在问“X 是什么/定义/概念/名词解释/对比”→ note_type=名词解释，必须保存到 名词解释/ 下。"
        "2) 如果在问“怎么做/实现/细节/排错/最佳实践/代码”→ note_type=技术实践，保存到合适的技术主题文件夹下，可用二级目录。"
        "示例："
        "- “RAG是什么”→ 名词解释/RAG.md"
        "- “RAG的分块与召回细节怎么调”→ 大模型技术/RAG/分块与召回调参.md"
        "- “Spring Boot Actuator怎么用”→ Java后端/Spring Boot/Actuator.md"
        "3) 尽量复用已有主题文件夹；若没有合适的允许新建。"
        "4) 名词解释的内容要更详细：定义、直观类比、关键要点、典型场景、常见误区、延伸阅读。"
        "5) 技术实践内容要可操作：步骤、配置、代码片段、注意事项、排错清单、下一步。"
        f"已存在的主题文件夹参考：{existing_s}"
    )
    user = (
        f"分类倾向：{category_hint}\n\n"
        "对话如下：\n"
        f"{convo}\n\n"
        "请生成学习笔记，优先抽取：关键问题、关键结论、代码/命令片段（如有）、易错点、下一步。"
    )
    msg = llm.invoke(
        [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ]
    )
    raw = str(getattr(msg, "content", "")).strip()
    try:
        data = json.loads(raw)
        if not isinstance(data, dict):
            return None, "json is not an object"
        return data, None
    except Exception as e:
        return None, f"json parse failed: {e}"


class NoteDecision(BaseModel):
    note_type: str = Field(description="只能是：名词解释 或 技术实践")
    topic_folder: str = Field(description="技术实践的保存目录（相对 study_files/），可多级目录。名词解释可为空。")
    title: str = Field(description="笔记标题（尽量简洁准确）")


def _llm_decide_note(
    settings: Settings,
    *,
    first_user_question: str,
    convo_text: str,
    existing_topic_folders: Optional[List[str]] = None,
) -> NoteDecision:
    """
    使用 LangChain 结构化输出做“类型+目录+标题”的决策。
    失败则回退到本地规则兜底。
    """
    existing = existing_topic_folders or []
    existing_s = "、".join(existing[:30]) if existing else "（无）"

    system = (
        "你是“问答辅助学习”助理。请只做“笔记归类决策”。\n"
        "规则：\n"
        "1) 若用户问“X是什么/定义/概念/名词解释/区别/对比”→ note_type=名词解释。\n"
        "2) 若用户问“怎么做/实现/细节/排错/最佳实践/代码/配置”→ note_type=技术实践。\n"
        "3) 名词解释必须保存到 名词解释/ 下（topic_folder 可留空）。\n"
        "4) 技术实践需要给出合适的 topic_folder，可用二级目录：例如 Java后端/Spring Boot、"
        "大模型技术/RAG 等；尽量复用已有目录；没有合适的允许新建。\n"
        f"已有主题目录参考：{existing_s}"
    )
    user = (
        f"用户首问：{first_user_question}\n\n"
        "对话片段：\n"
        f"{convo_text}\n\n"
        "请输出 note_type/topic_folder/title。"
    )

    llm = build_chat_llm(settings)
    try:
        llm_s = llm.with_structured_output(NoteDecision)
        d: NoteDecision = llm_s.invoke([SystemMessage(content=system), HumanMessage(content=user)])
        nt = (d.note_type or "").strip()
        tf = (d.topic_folder or "").strip()
        tt = (d.title or "").strip()
        if nt not in {"名词解释", "技术实践"}:
            nt = _guess_note_type(first_user_question)
        if not tt:
            tt = _safe_filename(first_user_question[:40] or "学习笔记", fallback="学习笔记")
        if nt == "名词解释":
            tf = ""
        return NoteDecision(note_type=nt, topic_folder=tf, title=tt)
    except Exception:
        nt = _guess_note_type(first_user_question)
        tf = "" if nt == "名词解释" else _guess_topic_folder(convo_text)
        tt = _safe_filename(first_user_question[:40] or "学习笔记", fallback="学习笔记")
        return NoteDecision(note_type=nt, topic_folder=tf, title=tt)


def _llm_generate_markdown(settings: Settings, *, decision: NoteDecision, convo_text: str) -> str:
    llm = build_chat_llm(settings)
    if decision.note_type == "名词解释":
        system = (
            "你是学习助理。请把内容写成“名词解释”类学习笔记，要求详细、结构清晰。"
            "必须包含：定义、直观类比、关键要点、典型场景、常见误区、延伸阅读。"
            "输出 Markdown。"
        )
    else:
        system = (
            "你是学习助理。请把内容写成“技术实践”类学习笔记，要求可操作。"
            "必须包含：目标、步骤、配置/代码片段（如有）、注意事项、排错清单、下一步。"
            "输出 Markdown。"
        )
    user = f"标题：{decision.title}\n\n对话片段：\n{convo_text}"
    msg = llm.invoke([SystemMessage(content=system), HumanMessage(content=user)])
    out = str(getattr(msg, "content", "") or "").strip()
    return out + ("\n" if out and not out.endswith("\n") else "")


def build_export_note_runnable(settings: Settings, study_root: Path):
    """
    LCEL pipeline：选择消息 →（结构化）决策 → 生成 Markdown → 落盘。
    """

    def _run(payload: Dict[str, Any]) -> StudyNoteResult:
        all_messages: List[Dict[str, str]] = payload["all_messages"]
        indices: List[int] = payload["indices_1based"]
        indices = sorted({max(1, int(i)) for i in indices if int(i) <= len(all_messages)})
        if not indices:
            raise ValueError("未选择任何消息。")

        sliced = [all_messages[i - 1] for i in indices]
        start_i, end_i = indices[0], indices[-1]

        merged_text = "\n".join((m.get("content") or "") for m in sliced).strip()
        category = _heuristic_category(merged_text)
        first_q = next((m.get("content", "").strip() for m in sliced if m.get("role") == "user"), "")

        existing_topics: List[str] = []
        try:
            if study_root.exists():
                for p in sorted(study_root.iterdir()):
                    if p.is_dir():
                        existing_topics.append(p.name)
        except Exception:
            existing_topics = []

        convo_for_model = merged_text[:8000]
        decision = _llm_decide_note(
            settings,
            first_user_question=first_q,
            convo_text=convo_for_model,
            existing_topic_folders=existing_topics,
        )

        base_folder = "名词解释" if decision.note_type == "名词解释" else _sanitize_folder_rel(
            decision.topic_folder or _guess_topic_folder(merged_text),
            fallback="未分类",
        )
        forced_path = f"{base_folder}/{_safe_filename(decision.title, fallback='学习笔记')}.md"
        rel_path = _sanitize_rel_path(forced_path, fallback=forced_path)

        # Avoid FileExistsError: auto-deduplicate filename
        def _dedupe_rel_path(rel: str) -> str:
            safe0 = resolve_under(study_root, rel)
            if not safe0.abs_path.exists():
                return rel
            p = Path(rel)
            parent = p.parent.as_posix()
            stem = p.stem
            suffix = p.suffix or ".md"
            for n in range(2, 100):
                cand = f"{stem} ({n}){suffix}"
                rel2 = f"{parent}/{cand}" if parent and parent != "." else cand
                safe2 = resolve_under(study_root, rel2)
                if not safe2.abs_path.exists():
                    return rel2
            # last resort: timestamp
            ts = datetime.now().strftime("%Y%m%d-%H%M%S")
            cand = f"{stem} ({ts}){suffix}"
            return f"{parent}/{cand}" if parent and parent != "." else cand

        rel_path = _dedupe_rel_path(rel_path)

        md = _llm_generate_markdown(settings, decision=decision, convo_text=convo_for_model)
        if not md:
            pairs = _pair_qa(sliced)
            md = _build_markdown_fallback(
                title=decision.title,
                category=category,
                items=pairs,
                start_i=start_i,
                end_i=end_i,
            )

        # use shared fs helpers for safe write under study_root
        safe = resolve_under(study_root, rel_path)
        write_text(safe.abs_path, md, encoding="utf-8")
        return StudyNoteResult(
            rel_path=rel_path,
            abs_path=str(safe.abs_path),
            markdown=md,
            title=decision.title,
            category=category,
        )

    return RunnableLambda(_run)


def generate_study_note(
    settings: Optional[Settings],
    all_messages: List[Dict[str, str]],
    start_i: int,
    end_i: int,
    study_root: Path,
    *,
    use_ai: bool = True,
) -> StudyNoteResult:
    """
    start_i/end_i 为 1-based，闭区间。
    """
    start_i = max(1, int(start_i))
    end_i = max(start_i, int(end_i))
    sliced = all_messages[start_i - 1 : end_i]
    merged_text = "\n".join((m.get("content") or "") for m in sliced)
    category = _heuristic_category(merged_text)
    pairs = _pair_qa(sliced)

    # Title heuristic
    first_q = next((m.get("content", "").strip() for m in sliced if m.get("role") == "user"), "")
    title = _safe_filename(first_q[:40] or "学习笔记", fallback="学习笔记")

    note_type = _guess_note_type(first_q)
    topic_folder = _guess_topic_folder(merged_text)
    md = _build_markdown_fallback(title=title, category=category, items=pairs, start_i=start_i, end_i=end_i)
    rel_path = _default_rel_path(title=title, note_type=note_type, topic_folder=topic_folder)

    if use_ai and settings is not None:
        existing_topics = []
        try:
            if study_root.exists():
                for p in sorted(study_root.iterdir()):
                    if p.is_dir():
                        existing_topics.append(p.name)
        except Exception:
            existing_topics = []

        data, _err = _llm_summarize_to_md(
            settings,
            sliced,
            category_hint=category,
            existing_topic_folders=existing_topics,
        )
        if isinstance(data, dict):
            nt = str(data.get("note_type") or "").strip()
            tf = str(data.get("topic_folder") or "").strip()
            t = str(data.get("title") or "").strip()
            rp = str(data.get("rel_path") or "").strip()
            mm = str(data.get("markdown") or "").strip()

            if nt in {"名词解释", "技术实践"}:
                note_type = nt
            # topic_folder 只在“技术实践”时生效；名词解释强制进 名词解释/
            if note_type != "名词解释":
                if tf:
                    topic_folder = tf
                else:
                    topic_folder = topic_folder or _guess_topic_folder(merged_text)
            if t:
                title = _safe_filename(t, fallback=title)
            # 最终路径强约束：完全不采纳模型 rel_path，避免回到年月日目录结构
            base_folder = "名词解释" if note_type == "名词解释" else _sanitize_folder_rel(topic_folder, fallback="未分类")
            forced_path = f"{base_folder}/{_safe_filename(title, fallback='学习笔记')}.md"
            rel_path = _sanitize_rel_path(forced_path, fallback=forced_path)
            if mm:
                md = mm + ("\n" if not mm.endswith("\n") else "")

    abs_path = resolve_under(study_root, rel_path).abs_path
    write_text(abs_path, md, encoding="utf-8", newline="\n", overwrite=True, mkdirs=True)
    return StudyNoteResult(
        rel_path=rel_path,
        abs_path=str(abs_path),
        markdown=md,
        title=title,
        category=category,
    )


def generate_study_note_from_indices(
    settings: Optional[Settings],
    all_messages: List[Dict[str, str]],
    indices_1based: List[int],
    study_root: Path,
    *,
    use_ai: bool = True,
) -> StudyNoteResult:
    """
    允许选择不连续消息（1-based indices）。
    """
    if not indices_1based:
        raise ValueError("未选择任何消息。")
    norm = sorted({max(1, int(i)) for i in indices_1based})
    norm = [i for i in norm if i <= len(all_messages)]
    if not norm:
        raise ValueError("所选消息超出范围。")

    sliced = [all_messages[i - 1] for i in norm]
    start_i, end_i = norm[0], norm[-1]

    merged_text = "\n".join((m.get("content") or "") for m in sliced)
    category = _heuristic_category(merged_text)
    pairs = _pair_qa(sliced)

    first_q = next((m.get("content", "").strip() for m in sliced if m.get("role") == "user"), "")
    title = _safe_filename(first_q[:40] or "学习笔记", fallback="学习笔记")

    note_type = _guess_note_type(first_q)
    topic_folder = _guess_topic_folder(merged_text)
    md = _build_markdown_fallback(title=title, category=category, items=pairs, start_i=start_i, end_i=end_i)
    rel_path = _default_rel_path(title=title, note_type=note_type, topic_folder=topic_folder)

    if use_ai and settings is not None:
        existing_topics = []
        try:
            if study_root.exists():
                for p in sorted(study_root.iterdir()):
                    if p.is_dir():
                        existing_topics.append(p.name)
        except Exception:
            existing_topics = []

        data, _err = _llm_summarize_to_md(
            settings,
            sliced,
            category_hint=category,
            existing_topic_folders=existing_topics,
        )
        if isinstance(data, dict):
            nt = str(data.get("note_type") or "").strip()
            tf = str(data.get("topic_folder") or "").strip()
            t = str(data.get("title") or "").strip()
            rp = str(data.get("rel_path") or "").strip()
            mm = str(data.get("markdown") or "").strip()

            if nt in {"名词解释", "技术实践"}:
                note_type = nt
            if note_type != "名词解释":
                if tf:
                    topic_folder = tf
                else:
                    topic_folder = topic_folder or _guess_topic_folder(merged_text)
            if t:
                title = _safe_filename(t, fallback=title)
            base_folder = "名词解释" if note_type == "名词解释" else _sanitize_folder_rel(topic_folder, fallback="未分类")
            forced_path = f"{base_folder}/{_safe_filename(title, fallback='学习笔记')}.md"
            rel_path = _sanitize_rel_path(forced_path, fallback=forced_path)
            if mm:
                md = mm + ("\n" if not mm.endswith("\n") else "")

    abs_path = resolve_under(study_root, rel_path).abs_path
    write_text(abs_path, md, encoding="utf-8", newline="\n", overwrite=True, mkdirs=True)
    return StudyNoteResult(
        rel_path=rel_path,
        abs_path=str(abs_path),
        markdown=md,
        title=title,
        category=category,
    )

