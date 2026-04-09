## 个人工作台 Agent（LangChain + Chroma + DeepSeek(OpenAI兼容) + Streamlit）

### 你将得到什么
- **Streamlit 前端**：上传资料、构建知识库、对话检索（RAG）。
- **Chroma 持久化向量库**：本地 `./data/chroma` 持久保存。
- **OpenAI 兼容接口**：用 `OPENAI_BASE_URL` 指向 DeepSeek，LangChain 侧用 `langchain-openai` 直接调用。

---

### 目录结构
- `app/streamlit_app.py`：Streamlit 入口
- `src/core/`：核心逻辑（配置、LLM、Agent、RAG 等）
- `src/services/`：服务层（文件扩充、MCP client、第三方集成等）
- `src/tools/`：运行时“工具模块”（会被 `import`，供服务/核心逻辑调用）
- `src/utils/`：通用辅助模块（纯函数/小封装，避免依赖复杂业务）
- `scripts/`：可执行脚本入口（只做 CLI 包装与参数解析，逻辑下沉到 `src/*`）
- `data/chroma/`：向量库持久化目录（自动生成）

目录约定（避免歧义）：
- **不要再新增顶层 `tools/` 目录**；需要命令行脚本请放 `scripts/`，需要可 import 的工具模块请放 `src/tools/` 或 `src/utils/`。
- **依赖方向**：`scripts/` → `src/*`；`src/*` 内部不要反向依赖 `scripts/`。

---

### 环境准备（Windows / PowerShell）

1) 使用现有 venv（你仓库里已有 `venv/`）

```bash
.\venv\Scripts\activate
python -m pip install -U pip
pip install -r requirements.txt
```

> 如果依赖安装在 Python 3.14 上遇到兼容性问题，建议改用 **Python 3.12/3.13** 新建 venv 再装依赖（LangChain/Chroma 生态通常更稳）。

2) 配置环境变量

```bash
copy .env.example .env
```

编辑 `.env`，填入你的 DeepSeek Key（以及必要时的模型名）。

3) 启动

```bash
.\run.ps1
```

也可以使用（CMD）：

```bash
run.bat
```

---

### 使用方式
- **上传并入库**：上传 `.txt/.md/.pdf`，点击“入库/更新知识库”
- **对话**：输入问题后，系统会先检索再生成回答，并展示引用片段

---

### Embeddings（向量化）可选：线上 API 或本地模型

本项目支持两种向量化方式（用于构建 Chroma 向量库）：

- **线上（默认）**：使用 OpenAI 兼容 embeddings API（例如 DeepSeek）
  - 需要：`DEEPSEEK_API_KEY`（或 `OPENAI_API_KEY`）以及 `EMBED_MODEL`
- **本地（推荐用于离线/省成本）**：使用 Sentence-Transformers / HuggingFace 模型（例如 `BAAI/bge-small-zh-v1.5`）
  - 配置：
    - `EMBEDDINGS_PROVIDER=local`
    - `LOCAL_EMBEDDINGS_MODEL=BAAI/bge-small-zh-v1.5`（或你的本地路径）
    - `LOCAL_EMBEDDINGS_DEVICE=cpu`（可选：`cuda`）

说明：
- **Embeddings 不一定需要 API**；但当前项目的“对话生成”（LLM Chat）仍需要 API Key。

