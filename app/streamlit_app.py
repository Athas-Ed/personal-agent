from __future__ import annotations

from src.utils.env import apply_runtime_env

apply_runtime_env()

import json
import sys
import os
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import streamlit as st
import altair as alt
import pandas as pd
from langchain_community.document_loaders import PyPDFLoader, TextLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter

from src.core.config import get_settings
from src.core.agent import run_with_tools_agent
from src.core.rag import answer_with_rag
from src.core.vectorstore import add_documents
from src.plugins.weather import get_weather_forecast
from src.services.file_expander import expand_markdown_file
from src.services.study_notes import build_export_note_runnable, generate_study_note, generate_study_note_from_indices
from src.tools.local_tools import build_export_tool_for_session
from src.utils.skills_registry import build_registry


st.set_page_config(page_title="粥米383的个人工作台", layout="wide")


def _load_docs_from_uploads(uploaded_files) -> List:
    docs = []
    with tempfile.TemporaryDirectory() as tmpdir:
        for uf in uploaded_files:
            name = uf.name
            suffix = os.path.splitext(name)[1].lower()
            path = os.path.join(tmpdir, name)
            with open(path, "wb") as f:
                f.write(uf.getbuffer())

            if suffix in [".txt", ".md"]:
                file_docs = TextLoader(path, encoding="utf-8").load()
            elif suffix == ".pdf":
                file_docs = PyPDFLoader(path).load()
            else:
                raise ValueError(f"暂不支持的文件类型：{suffix}（仅支持 .txt/.md/.pdf）")

            # Record source for later citation
            for d in file_docs:
                d.metadata.setdefault("source", name)

            docs.extend(file_docs)
    return docs


def _load_docs_from_study_files(study_root: Path, *, exts: Optional[List[str]] = None) -> List:
    """
    扫描 study_files/ 下的资料并加载为 LangChain Documents。
    - 仅加载文本/Markdown/PDF（与上传入库保持一致）
    - metadata.source 记录为相对 study_files 的路径，便于引用展示
    """
    exts = exts or [".txt", ".md", ".pdf"]
    exts_n = {e.lower() if e.startswith(".") else f".{e.lower()}" for e in exts}

    if not study_root.exists():
        return []

    docs: List = []
    for p in sorted(study_root.rglob("*")):
        if not p.is_file():
            continue
        if p.suffix.lower() not in exts_n:
            continue

        rel = p.relative_to(study_root).as_posix()
        suffix = p.suffix.lower()
        if suffix in [".txt", ".md"]:
            file_docs = TextLoader(str(p), encoding="utf-8").load()
        elif suffix == ".pdf":
            file_docs = PyPDFLoader(str(p)).load()
        else:
            continue

        for d in file_docs:
            d.metadata.setdefault("source", f"study_files/{rel}")

        docs.extend(file_docs)
    return docs


def main():
    if "messages" not in st.session_state:
        st.session_state.messages = []
    if "dev_mode" not in st.session_state:
        st.session_state.dev_mode = False
    if "pending_prompt" not in st.session_state:
        st.session_state.pending_prompt = None
    if "note_selected" not in st.session_state:
        st.session_state.note_selected = set()
    if "weather_city" not in st.session_state:
        st.session_state.weather_city = "太原"
    if "use_tools_agent" not in st.session_state:
        st.session_state.use_tools_agent = True

    title_cols = st.columns([0.86, 0.14])
    with title_cols[0]:
        st.title("粥米383的个人工作台")
        st.caption("问答辅助学习 · LangChain + DeepSeek(OpenAI兼容) + Streamlit")
    with title_cols[1]:
        st.session_state.dev_mode = st.toggle("开发者", value=bool(st.session_state.dev_mode))

    try:
        settings = get_settings()
    except Exception as e:
        st.error(str(e))
        st.stop()

    def _load_skill_registry() -> Dict[str, Any]:
        p = Path("skills/registry.json")
        if not p.exists():
            return {"skills": [], "errors": []}
        try:
            return json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            return {"skills": [], "errors": [{"dir": "registry.json", "error": "invalid json"}]}

    with st.sidebar:
        if st.session_state.dev_mode:
            with st.expander("技能快捷入口（开发者）", expanded=False):
                if st.button("刷新技能", type="primary"):
                    try:
                        reg = build_registry(Path("skills"))
                        Path("skills/registry.json").write_text(
                            json.dumps(reg, ensure_ascii=False, indent=2),
                            encoding="utf-8",
                        )
                        st.success(f"已刷新：{len(reg.get('skills', []))} 个技能")
                        if reg.get("errors"):
                            st.warning("部分技能有问题（不影响其他技能）：")
                            st.json(reg["errors"])
                    except Exception as e:
                        st.error(f"刷新失败：{e}")

                reg = _load_skill_registry()
                skills = reg.get("skills") or []
                # 固定高度滚动区域：让技能区整体篇幅锁定
                with st.container(height=170, border=True):
                    if not skills:
                        st.caption("暂无技能。把技能文件夹放到 `skills/` 后点“刷新技能”。")
                    for s in skills:
                        name = str(s.get("name") or s.get("dir") or "skill").strip()
                        if st.button(name, key=f"skill_btn_{s.get('dir')}", use_container_width=True):
                            st.session_state.pending_prompt = f"请启用技能「{name}」来帮助我完成接下来的需求：\n\n"

        st.divider()
        st.subheader("学习笔记导出")
        total = len(st.session_state.messages)
        if st.button("刷新内容"):
            st.rerun()
        if total == 0:
            st.caption("开始对话后，这里可以选择消息并导出为 Markdown，保存到 `study_files/`。")
        else:
            mode = st.radio("选择方式", options=["逐条勾选", "起止区间"], horizontal=True)
            st.caption("提示：序号按对话显示顺序计数（1,2,3...）。")

            if mode == "逐条勾选":
                btns = st.columns(3)
                if btns[0].button("全选"):
                    st.session_state.note_selected = set(range(1, total + 1))
                    st.rerun()
                if btns[1].button("清空"):
                    st.session_state.note_selected = set()
                    st.rerun()
                if btns[2].button("选最近10条"):
                    st.session_state.note_selected = set(range(max(1, total - 9), total + 1))
                    st.rerun()

                # 性能优化：避免为每条消息渲染一个 checkbox（会导致每次点击都很卡）。
                # 用 form + multiselect，让用户一次性选好再“应用”，大幅减少重跑开销。
                options = list(range(1, total + 1))

                def _fmt_opt(i: int) -> str:
                    try:
                        m = st.session_state.messages[i - 1]
                        role = "我" if m.get("role") == "user" else "助手"
                        text = (m.get("content") or "").replace("\n", " ").strip()
                        preview = text[:60] + ("…" if len(text) > 60 else "")
                        return f"#{i} [{role}] {preview}"
                    except Exception:
                        return f"#{i}"

                with st.form("note_select_form", border=True):
                    picked = st.multiselect(
                        "选择要导出的消息（可不连续）",
                        options=options,
                        default=sorted(st.session_state.note_selected),
                        format_func=_fmt_opt,
                    )
                    applied = st.form_submit_button("应用选择")
                if applied:
                    st.session_state.note_selected = set(int(x) for x in picked)
                    st.rerun()

                selected = sorted(st.session_state.note_selected)
                if st.button("AI整理并保存", type="primary", disabled=not selected):
                    try:
                        study_root = Path("study_files")
                        with st.spinner("AI 整理中..."):
                            runnable = build_export_note_runnable(settings, study_root=study_root)
                            res = runnable.invoke(
                                {"all_messages": st.session_state.messages, "indices_1based": selected}
                            )
                        st.success(f"已保存：`study_files/{res.rel_path}`")
                        with st.expander("预览"):
                            st.markdown(res.markdown)
                    except Exception as e:
                        st.error(f"保存失败：{e}")

            else:
                start_i = st.number_input(
                    "起始序号（含）",
                    min_value=1,
                    max_value=total,
                    value=max(1, total - 5),
                    step=1,
                )
                end_i = st.number_input("结束序号（含）", min_value=1, max_value=total, value=total, step=1)
                if st.button("AI整理并保存", type="primary"):
                    try:
                        study_root = Path("study_files")
                        with st.spinner("AI 整理中..."):
                            res = generate_study_note(
                                settings=settings,
                                all_messages=st.session_state.messages,
                                start_i=int(start_i),
                                end_i=int(end_i),
                                study_root=study_root,
                                use_ai=True,
                            )
                        st.success(f"已保存：`study_files/{res.rel_path}`")
                        with st.expander("预览"):
                            st.markdown(res.markdown)
                    except Exception as e:
                        st.error(f"保存失败：{e}")

        st.divider()
        st.subheader("对话引擎")
        st.session_state.use_tools_agent = st.toggle("自动工具调用（推荐）", value=bool(st.session_state.use_tools_agent))
        st.caption("开启后，你只要提出要求，助手会自行判断并调用工具（如查询天气、导出学习笔记等）。")
        with st.expander("环境与工具可用性"):
            st.code(f"python={sys.executable}")
            ok_mcp = True
            err_mcp = ""
            try:
                import langchain_mcp_adapters  # type: ignore
            except Exception as e:
                ok_mcp = False
                err_mcp = str(e)
            st.markdown(f"- **langchain_mcp_adapters**：{'可用' if ok_mcp else '不可用'}")
            if err_mcp:
                st.caption(err_mcp)

            st.divider()
            st.markdown("**本地 MCP（stdio）快速体验**")
            st.caption("点击按钮调用本地 MCP server 的 `list_study_files`，验证 MCP 是否正常工作。")
            if st.button("MCP：列出 study_files 文件", disabled=not ok_mcp):
                try:
                    from src.services.mcp_client import MCPClientService

                    mcp = MCPClientService.get_instance(settings=settings)
                    res = mcp.call_tool(
                        "list_study_files",
                        {"exts": [".md", ".txt", ".pdf"], "limit": 200, "contains": ""},
                    )
                    st.json(res)
                except Exception as e:
                    st.error(f"MCP 调用失败：{e}")

        st.divider()
        st.subheader("本地文件扩充（Markdown）")
        st.caption("读取并扩充某个本地 .md 文件，可输出为新文件或覆盖写回。")
        scope = st.radio("范围", options=["study_files（更安全）", "repo（整个项目）"], horizontal=True)
        base_dir = Path("study_files") if scope.startswith("study_files") else Path(".")
        input_path = st.text_input(
            "输入文件路径（相对所选范围）",
            value="名词解释/LangChain是什么？.md" if base_dir.as_posix() == "study_files" else "study_files/名词解释/LangChain是什么？.md",
        )
        output_path = st.text_input("输出文件路径（可留空，默认生成 .expanded.md）", value="")
        overwrite = st.checkbox("允许覆盖输出文件", value=False)

        if st.button("AI扩充并保存", type="primary"):
            try:
                with st.spinner("AI 扩充中..."):
                    res = expand_markdown_file(
                        settings=settings,
                        input_path=input_path,
                        output_path=output_path.strip() or None,
                        base_dir=base_dir,
                        overwrite=bool(overwrite),
                    )
                st.success(f"已保存：`{base_dir.as_posix().rstrip('/')}/{res.output_rel_path}`")
                with st.expander("预览"):
                    st.markdown(res.markdown)
            except Exception as e:
                st.error(f"扩充失败：{e}")

        st.divider()
        if st.session_state.dev_mode:
            st.subheader("开发者设置")
            st.caption("这里是底层参数与诊断功能；日常学习问答不需要动。")

            if st.button("API 连通性测试（DeepSeek）"):
                try:
                    from src.core.llm import build_chat_llm

                    llm = build_chat_llm(settings)
                    msg = llm.invoke(
                        [
                            {"role": "system", "content": "你是连通性测试助手。只回答 OK。"},
                            {"role": "user", "content": "ping"},
                        ]
                    )
                    st.success(f"连通性正常：{str(getattr(msg, 'content', '')).strip()[:40] or 'OK'}")
                except Exception as e:
                    st.error(f"连通性失败：{e}")

            st.divider()
            st.subheader("知识库（可选）")
            kb_source = st.radio(
                "入库来源",
                options=["上传文件", "study_files 文件夹（批量）"],
                horizontal=True,
            )
            uploaded = st.file_uploader(
                "上传资料（.txt/.md/.pdf）",
                type=["txt", "md", "pdf"],
                accept_multiple_files=True,
            )
            chunk_size = st.number_input("chunk_size", min_value=200, max_value=4000, value=900, step=50)
            chunk_overlap = st.number_input("chunk_overlap", min_value=0, max_value=800, value=150, step=10)

            if kb_source.startswith("上传"):
                disabled = not uploaded
            else:
                disabled = False

            if st.button("入库 / 更新知识库", disabled=disabled):
                try:
                    if kb_source.startswith("上传"):
                        raw_docs = _load_docs_from_uploads(uploaded)
                    else:
                        study_root = Path("study_files")
                        raw_docs = _load_docs_from_study_files(study_root)
                        if not raw_docs:
                            st.warning("未在 `study_files/` 下找到可入库文件（仅扫描 .txt/.md/.pdf）。")
                            st.stop()

                    splitter = RecursiveCharacterTextSplitter(
                        chunk_size=int(chunk_size),
                        chunk_overlap=int(chunk_overlap),
                    )
                    split_docs = splitter.split_documents(raw_docs)
                    n = add_documents(settings, split_docs)
                    st.success(f"入库完成：写入 {n} 条向量。持久化目录：{settings.chroma_persist_dir}")
                except Exception as e:
                    st.error(f"入库失败：{e}")

            st.divider()
            st.subheader("当前配置")
            st.code(
                "\n".join(
                    [
                        f"OPENAI_BASE_URL={settings.openai_base_url}",
                        f"CHAT_MODEL={settings.chat_model}",
                        f"EMBED_MODEL={settings.embed_model}",
                        f"COLLECTION_NAME={settings.collection_name}",
                        f"CHROMA_PERSIST_DIR={settings.chroma_persist_dir}",
                    ]
                )
            )

    main_cols = st.columns([0.66, 0.34], gap="large")

    with main_cols[0]:
        st.subheader("对话（学习问答）")

        for idx, m in enumerate(st.session_state.messages, start=1):
            with st.chat_message(m["role"]):
                st.caption(f"#{idx}")
                st.markdown(m["content"])

        if st.session_state.pending_prompt:
            st.info("已选择技能：下一条输入会带上技能引导文本。")

        prompt = st.chat_input("请输入问题（学习问答/编程/AI/生活常识都可以）")
        if prompt or st.session_state.pending_prompt:
            final_prompt = (st.session_state.pending_prompt or "") + (prompt or "")
            st.session_state.pending_prompt = None

            st.session_state.messages.append({"role": "user", "content": final_prompt})
            with st.chat_message("user"):
                st.markdown(final_prompt)

            with st.chat_message("assistant"):
                with st.spinner("思考中..."):
                    try:
                        if st.session_state.use_tools_agent:
                            session_tools = [
                                build_export_tool_for_session(settings, session_messages=st.session_state.messages)
                            ]
                            run = run_with_tools_agent(
                                settings=settings,
                                user_input=final_prompt,
                                session_messages=st.session_state.messages,
                                tools=session_tools,
                            )
                            st.markdown(run.output)
                            if run.tool_events:
                                with st.expander("工具调用轨迹"):
                                    st.markdown(f"- **MCP tools**：{'已加载' if run.mcp_tools_loaded else '未加载'}")
                                    for i, ev in enumerate(run.tool_events, start=1):
                                        st.markdown(f"**[{i}] {ev.tool_name}**  {'✅' if ev.ok else '❌'}")
                                        st.json({"args": ev.tool_args, "result_preview": ev.result_preview})
                            st.session_state.messages.append({"role": "assistant", "content": run.output})
                        else:
                            # 默认主流程以“学习问答”为主：优先纯对话；如你在开发者页启用知识库后再依赖 RAG。
                            result = answer_with_rag(settings, final_prompt, k=4)
                            st.markdown(result.answer)
                            if result.sources:
                                with st.expander("引用片段"):
                                    for i, (src, preview) in enumerate(result.sources, start=1):
                                        st.markdown(f"**[{i}] {src}**\n\n{preview}")
                            st.session_state.messages.append({"role": "assistant", "content": result.answer})
                    except Exception as e:
                        st.error(f"生成失败：{e}")

    with main_cols[1]:
        st.subheader("查询天气")
        hot_cities = ["太原", "北京", "上海", "广州", "深圳", "杭州", "成都", "重庆", "武汉", "西安", "南京", "自定义…"]
        # 默认太原（内部状态记忆）
        current = st.session_state.weather_city or "太原"
        try:
            default_idx = hot_cities.index(current) if current in hot_cities else 0
        except Exception:
            default_idx = 0
        city_pick = st.selectbox("城市", options=hot_cities, index=default_idx, key="weather_pick")
        if city_pick == "自定义…":
            city_maps = st.text_input("输入城市", value=current if current else "太原", key="weather_city_input")
        else:
            city_maps = city_pick
        st.session_state.weather_city = city_maps

        if st.button("查询", type="primary", key="weather_query"):
            try:
                data = get_weather_forecast(city_maps)
                if not isinstance(data, dict):
                    st.json(data)
                elif data.get("error"):
                    st.error(str(data.get("error")))
                    st.json(data)
                else:
                    city = data.get("city") or city_maps
                    forecasts = data.get("forecasts") or []

                    st.markdown(f"**{city}** 未来天气（高德 MCP）")
                    if forecasts:
                        today = forecasts[0]
                        cols = st.columns(4)
                        cols[0].metric("白天", f"{today.get('dayweather','-')}")
                        cols[1].metric("白天温度", f"{today.get('daytemp','-')} ℃")
                        cols[2].metric("夜间", f"{today.get('nightweather','-')}")
                        cols[3].metric("夜间温度", f"{today.get('nighttemp','-')} ℃")

                        rows = []
                        for f in forecasts:
                            rows.append(
                                {
                                    "date": f.get("date"),
                                    "daytemp": float(f.get("daytemp_float") or f.get("daytemp") or 0),
                                    "nighttemp": float(f.get("nighttemp_float") or f.get("nighttemp") or 0),
                                    "dayweather": f.get("dayweather"),
                                    "nightweather": f.get("nightweather"),
                                }
                            )

                        df = pd.DataFrame(rows)
                        if not df.empty:
                            try:
                                df["date"] = pd.to_datetime(df["date"], errors="coerce")
                            except Exception:
                                pass

                            df_m = df.melt(
                                id_vars=["date"],
                                value_vars=["daytemp", "nighttemp"],
                                var_name="which",
                                value_name="temp_c",
                            )
                            df_m["which"] = df_m["which"].map({"daytemp": "白天", "nighttemp": "夜间"})

                            base = (
                                alt.Chart(df_m)
                                .encode(
                                    x=alt.X("date:T", title="日期", axis=alt.Axis(format="%m-%d")),
                                    y=alt.Y("temp_c:Q", title="温度(℃)"),
                                    color=alt.Color("which:N", title="时段"),
                                    tooltip=["date:T", "which:N", "temp_c:Q"],
                                )
                            )
                            line = base.mark_line(point=True)
                            labels = base.mark_text(dy=-10).encode(text=alt.Text("temp_c:Q", format=".0f"))
                            base_chart = line + labels

                            st.altair_chart(base_chart.properties(height=320), use_container_width=True)
                    else:
                        st.info("未返回 forecasts 数据。")
            except Exception as e:
                st.error(f"查询失败：{e}")


if __name__ == "__main__":
    main()

