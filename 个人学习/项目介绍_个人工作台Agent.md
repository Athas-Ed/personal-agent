# 项目介绍：个人工作台 Agent（Streamlit + LangChain + Chroma + MCP）

> 面向老师/评审的项目概览文档（偏“架构与实现”）。  
> 仓库定位：一个**本地可运行的个人学习工作台**，支持对话问答、资料入库与检索（RAG）、自动工具调用、学习笔记整理导出，并预留可扩展的 MCP 工具接入能力。

---

## 项目目标与定位

- **目标**：搭建一个“学习 + 资料管理 + 工具调用”的个人工作台，让用户可以：
  - 在网页端对话提问（一般问答 / 学习问答）。
  - 上传 `.txt/.md/.pdf` 资料构建本地知识库，进行检索增强回答（RAG）。
  - 让模型在需要时自动调用工具（例如：查询天气、合并/扩充 Markdown、导出学习笔记等）。
  - 把对话整理为结构化学习笔记并写入 `study_files/`，形成个人知识沉淀。
- **风格**：尽量工程化地把能力拆分到 `core / services / tools / plugins / integrations`，并通过约束与兜底机制保证：
  - 基础对话始终可用（RAG 失败自动降级）。
  - 文件读写受控（安全路径与确认开关）。
  - MCP 工具可选加载（失败不影响主流程）。

---

## 技术栈（依赖与核心组件）

### 运行环境

- **语言**：Python
- **主要运行平台**：Windows（仓库提供 `run.bat`、`run.ps1` 启动脚本）
- **环境变量**：使用 `.env` 配置（项目内通过统一入口加载）

### 前端/UI

- **Streamlit**：单页应用形式的交互界面（主入口：`app/streamlit_app.py`）
- **Altair + Pandas**：用于天气温度趋势可视化与数据表处理

### LLM / Agent 框架

- **LangChain（0.3+）**
  - `langchain-openai`：对 **OpenAI 兼容接口** 的 Chat/Embedding 客户端封装（本项目用于对接 DeepSeek 的 OpenAI 兼容 API）
  - `LCEL / Runnable`：用 `RunnableLambda` 把消息构造、工具循环封装为可组合链路
  - **Tool schema + bind_tools + ToolMessage**：实现 tool-calling

### 知识库与 RAG

- **ChromaDB** + **langchain-chroma**：本地持久化向量库（默认 `./data/chroma`）
- **pypdf**：PDF 文档加载
- **langchain-text-splitters**：文档分块（`RecursiveCharacterTextSplitter`）

### MCP（Model Context Protocol）

- **mcp**：本地 MCP server 框架（FastMCP）
- **langchain-mcp-adapters**：MCP client，并将 MCP 工具适配为 LangChain Tools
- 本项目同时示例了两类 MCP：
  - **本地 stdio MCP Server**：`mcp/server.py`（由本项目子进程启动）
  - **第三方 Streamable HTTP MCP**：高德地图 MCP（天气能力），见 `src/integrations/amap_weather_mcp.py`

---

## 快速运行（Windows）

### 1) 安装依赖

- 仓库自带 `venv/` 时可直接激活使用；若要重新创建：
  - 创建 venv
  - `pip install -r requirements.txt`

### 2) 配置 `.env`

- 复制模板：`.env.example` → `.env`
- 关键配置（概念层面）：
  - **大模型接口**：`DEEPSEEK_API_KEY / DEEPSEEK_BASE_URL`（或 `OPENAI_API_KEY / OPENAI_BASE_URL`）
  - **模型名**：`CHAT_MODEL / EMBED_MODEL`
  - **MCP**：`MCP_ENABLE`、`MCP_TOOLS_TTL_S`、`MCP_PYTHON`（可选）
  - **高德**：`AMAP_KEY`（可选；缺失则天气插件自动不可用）

### 3) 启动

- PowerShell：`run.ps1`
- CMD：`run.bat`

启动脚本的工程化处理（`run.bat`）：
- 强制要求 `venv\Scripts\python.exe` 与 `.env` 存在
- 将 `.env` 解析为临时 `.cmd` 并注入当前进程环境（`scripts/env_to_cmd.py` → `src/utils/env_cmd.py`）
- 将 `DEEPSEEK_*` 映射到 `OPENAI_*`（便于复用 OpenAI 兼容客户端）
- 清理异常 CA 环境变量（避免代理注入 `$ca` 导致 httpx 初始化报错）
- 可选处理企业/代理场景的 CA（WATT CA）

---

## 项目结构（目录分层与职责）

依据 `README.md` 的约定，核心目录如下：

```text
app/
  streamlit_app.py          # Streamlit 入口（UI + 会话状态 + 调用 core/services）

src/
  core/                     # 核心引擎：Settings/LLM/RAG/向量库/Agent链路
  services/                 # 服务层：文件扩充、笔记整理导出、MCP client 等
  tools/                    # “可被 Agent 调用”的工具封装（StructuredTool/BaseTool）
  plugins/                  # 可插拔能力（例如天气），避免 core 硬依赖
  integrations/             # 第三方系统集成细节（例如高德 MCP）
  utils/                    # 通用工具：env/证书/同步桥/技能注册表等

mcp/
  server.py                 # 本地 MCP Server（stdio）

skills/
  <skill_name>/SKILL.md     # 技能包（以文档/流程为主，可带 scripts/）
  registry.json             # 技能索引（由脚本生成）

study_files/                # 学习笔记与资料（上传/导出/扩充/合并等默认在此范围操作）
data/chroma/                # Chroma 向量库持久化目录（自动生成）
scripts/                    # CLI脚本入口（逻辑下沉到 src/）
```

分层依赖约束（仓库约定）：
- `scripts/` → `src/*`
- `src/*` 内部不要反向依赖 `scripts/`
- 工具定义（schema）放 `src/tools`；复杂业务逻辑尽量下沉到 `src/services`

---

## 核心能力与实现细节（按“链路”解释）

### 1) Streamlit UI：会话状态 + 多功能面板

入口 `app/streamlit_app.py` 做的事情可概括为：
- **会话状态**：维护 `messages`、开发者模式、笔记选择区间、城市选择、是否启用 tools-agent 等
- **对话区**：
  - 用户输入后写入 `st.session_state.messages`
  - 根据开关选择：
    - **自动工具调用（推荐）**：走 `run_with_tools_agent`
    - **纯对话/RAG**：走 `answer_with_rag`
  - 可选显示“工具调用轨迹”（调用哪个工具、参数、结果预览、是否加载 MCP tools）
- **学习笔记导出区**：
  - 支持逐条选择或起止区间
  - 通过 `build_export_note_runnable` 将对话整理成 Markdown 并落盘到 `study_files/`
  - 额外做了性能优化：用 `form + multiselect` 替代大量 checkbox，避免 Streamlit 重跑卡顿
- **知识库（可选）**：
  - 上传资料 → 文档加载 → 分块 → 写入 Chroma
- **本地 Markdown 扩充**：
  - 支持限定范围 `study_files` 或整个仓库 `repo`
  - 调用 `expand_markdown_file` 生成扩充版笔记
- **天气查询**：
  - 调用高德 MCP 获取未来预报，并用 Altair 画温度趋势

### 2) 配置与环境治理：确保“入口一致”

统一配置入口：`src/core/config.py`
- `get_settings()` 会读取 `.env` 与环境变量，构造 `Settings`
- 支持 `DEEPSEEK_*` / `OPENAI_*` 两套命名（优先 DeepSeek 命名）

统一在最早阶段加载 `.env` 并清理异常 CA：
- `src/utils/env.py`：`apply_runtime_env() = load_project_env() + sanitize_ca_env()`
- `sitecustomize.py`：Python 启动自动导入（安全失败），尽量保证所有入口统一生效
- `src/core/llm.py`：构造 httpx client 时再次做 SSL 环境兜底清理与证书策略（系统证书 + certifi + 可选自定义 CA bundle），并支持代理环境变量

### 3) LLM 接入：OpenAI 兼容（DeepSeek）

`src/core/llm.py`
- `build_chat_llm()`：`ChatOpenAI(api_key, base_url, model, temperature, http_client=...)`
- `build_embeddings()`：`OpenAIEmbeddings(...)`

工程要点：
- **httpx 客户端自建**：集中处理代理、证书校验开关、CA bundle 追加加载
- **Windows/企业代理场景**：尽量使用 `ssl.create_default_context()` 兼容系统证书库

### 4) RAG：Chroma 向量库 + 降级策略

`src/core/vectorstore.py`
- `get_vectorstore()`：用 `Chroma(persist_directory=..., embedding_function=...)`
- `add_documents()`：写入并返回写入数量

`src/core/rag.py`
- `answer_with_rag()`：
  - 如果向量库为空/检索失败/embedding 失败 → **自动降级为纯对话**
  - 否则：`retriever.invoke(question)` 取 `k` 条，拼接 context，交给 LLM 生成答案
  - 同时返回 sources（source metadata + preview），UI 可展示引用片段

这保证了“知识库不是硬依赖”，系统可在任何阶段可用。

### 5) Tools-Agent：LCEL 链路 + Tool-Calling Loop

目标：用户只提出需求，模型可以自己选择工具并调用。

关键模块：

1) **系统提示词**：`src/core/prompts.py`
- 约束：文件操作默认 `scope=study_files`；写入类工具必须在用户明确要求保存/导出时才调用并带确认参数

2) **消息构造 Runnable**：`src/core/message_chain.py`
- `build_messages_runnable()`：把 `system + 历史对话 + 当前用户输入` 转成 LangChain messages

3) **工具注册表（bundle）**：`src/tools/tool_registry.py`
- `build_tools_bundle()`：
  - 可注入 `extra_tools`（例如“绑定当前会话”的导出工具）
  - 可选加载 MCP tools（失败则 `mcp_loaded=False` 不影响主流程）
  - 加载本地 tools（搜索/合并/扩充/可选插件等）
  - 去重（按 tool.name）

4) **Tool-Calling Loop**：`src/core/tool_calling_chain.py`
- 模型输出 `tool_calls` → 逐个执行 `tool.invoke(args)` → 追加 `ToolMessage` 回填 → 直到不再请求工具或达到 `max_tool_iters`
- 对 tool args 做了兼容归一化（dict / JSON string / plain string）
- 记录事件（tool_name/args/ok/result_preview），供 UI 展示“工具调用轨迹”

5) **整体链路封装**：`src/core/tools_agent_chain.py` + `src/core/agent.py`
- `build_tools_agent_chain()`：组装 `system + messages + llm.bind_tools(tools) + loop`
- `run_with_tools_agent()`：对外返回 `final_text + tool_events + MCP 加载情况`

### 6) 本地工具（Local Tools）：以“受控文件操作”为主

`src/tools/local_tools.py`

- **模糊搜索文件名**：`fuzzy_search_files`
  - 只按路径名匹配，不读内容，速度快
  - 默认范围 `study_files`，可切换到 `repo`
- **合并 Markdown**：`merge_markdown_files`
  - 调用 `src/services/markdown_merger.py`，用 LLM 合并去重并在文末列出来源文件
  - 可选删除输入文件（必须 `confirm_delete=True`）
- **扩充 Markdown**：`expand_markdown_file`
  - 调用 `src/services/file_expander.py`，扩充定义/要点/误区/对比/下一步等
- **会话绑定导出工具**：`export_study_note`
  - 通过闭包绑定当前会话 `session_messages`
  - **强约束**：必须 `confirm_write=True` 才允许落盘（防止模型误写）

安全机制（文件系统约束）：
- `src/tools/fs.py`：`resolve_under(base_dir, user_path)` 强制路径必须位于 base_dir 下，禁止 `..` 穿越
- `services` 层（merge/expand/note）也采用同类约束，默认优先在 `study_files/` 范围操作

### 7) MCP：本地工具服务器 + 第三方工具接入示例

#### 7.1 本地 MCP Server（stdio）

`src/mcp/server.py`
- `FastMCP("personal-workbench-mcp")`
- 示例工具：
  - `ping`
  - `now_iso`
  - `expand_local_markdown`：调用本项目 `expand_markdown_file`

`src/services/mcp_client.py`
- `MCPClientService`：单例，负责启动/连接 MCP server 并缓存 tools（TTL）
- 默认优先使用本项目 `venv\Scripts\python.exe` 启动 server，避免子进程缺依赖
- 通过 `langchain-mcp-adapters` 的 `MultiServerMCPClient` 拉取工具并适配为 LangChain tools

`src/tools/mcp_tools.py`
- 将 MCP tools 作为“可选工具集合”注入 tools-agent 的 bundle 中

#### 7.2 第三方 MCP（高德地图，Streamable HTTP）

`src/integrations/amap_weather_mcp.py`
- 通过 `AMAP_KEY` 生成 Streamable HTTP MCP URL
- 自建 httpx client factory（代理/证书/CA bundle 处理）
- tools 缓存（TTL）
- `guess_weather_tool_name()`：从工具列表中猜测包含 `weather` 的工具名

`src/plugins/weather.py`
- 作为“可插拔插件”对外提供稳定函数 `get_weather_forecast(city)`
- 若未配置 `AMAP_KEY`，`build_weather_tool()` 返回 `None`，即插件不会进入 tools 列表

---

## “技能系统”（skills/）在项目中的角色

该仓库同时维护了一套 **Skills 目录规范**（偏“方法论/流程/提示词”），用于把常用任务的步骤与注意事项沉淀为 `SKILL.md`。

相关实现：
- `skills/README.md`：技能目录规范与模板
- `src/utils/skills_registry.py`：扫描 `skills/*/SKILL.md` 的 YAML frontmatter，生成 `skills/registry.json`
- `scripts/sync_skills.py`：命令行生成 registry
- `app/streamlit_app.py`：开发者模式下可刷新并提供“技能快捷入口”，点击后会把引导文本注入下一次对话输入

设计意图：
- **skills** 更像“可复用 SOP/Prompt 工程资产”
- **tools/services** 更像“可执行能力/确定性逻辑”

---

## 工程化亮点（可作为汇报要点）

- **链路可组合（LCEL）**：把消息构建、工具循环等封装为 Runnable，便于扩展 tracing/测试/替换组件
- **工具注册表模式**：集中管理本地工具与 MCP 工具的加载、去重与可选性
- **强约束文件写入**：`confirm_write`、安全路径限制 `resolve_under`、默认 scope=study_files，减少模型误操作风险
- **RAG 降级策略**：向量库空/检索失败时回退到纯对话，保证可用性
- **Windows/代理/证书治理**：对 `.env` 注入、CA 环境变量清理、证书上下文策略做了完整兜底
- **可插拔插件**：天气能力不成为 core 硬依赖，缺 key 自动降级
- **Streamlit 性能优化实践**：大量选择项改用 `form + multiselect`，减少重跑开销

---

## 可扩展方向（后续迭代建议）

- **工具层面**：
  - 增加文件内容检索（在安全范围内）与“引用片段”生成
  - 增加任务管理、日程、项目看板等本地工具（并作为 MCP tool 暴露）
- **RAG 层面**：
  - 增加重排（rerank）、更精细的 chunk 策略、source 引用更精确的定位
  - 增加多集合/多主题知识库管理
- **工程与质量**：
  - 增加基础单测（例如路径安全、工具参数校验、RAG 降级路径）
  - 对 tool-calling loop 增加更严格的“写入必须二次确认”策略（UI 级别）

---

## 关键文件索引（方便老师快速翻阅）

- **项目说明/运行**：`README.md`、`run.bat`、`run.ps1`、`requirements.txt`
- **UI 入口**：`app/streamlit_app.py`
- **核心配置**：`src/core/config.py`
- **LLM 接入**：`src/core/llm.py`
- **RAG**：`src/core/rag.py`、`src/core/vectorstore.py`
- **Tools-Agent 链路**：`src/core/tools_agent_chain.py`、`src/core/message_chain.py`、`src/core/tool_calling_chain.py`、`src/core/agent.py`
- **本地工具**：`src/tools/local_tools.py`、`src/tools/tool_registry.py`、`src/tools/fs.py`
- **学习笔记导出**：`src/services/study_notes.py`
- **Markdown 扩充/合并**：`src/services/file_expander.py`、`src/services/markdown_merger.py`
- **MCP（本地）**：`src/mcp/server.py`、`src/services/mcp_client.py`、`src/tools/mcp_tools.py`
- **MCP（高德天气）**：`src/integrations/amap_weather_mcp.py`、`src/plugins/weather.py`

