## 基于 LangChain 的项目架构设计要点（本项目落地版）

这份文档总结了本项目在 **LangChain 框架**下，应该尽量遵循的工程化规范：分层边界、链路表达、Tools 规范、可插拔能力、MCP 集成与配置收敛。

---

## 1) 分层规范：把“编排”和“能力”解耦

### 推荐分层（本项目）
- **`src/core/`**：核心编排层  
  负责“怎么组合”：system prompt、消息构建、是否启用 tools、调用循环/链路执行。  
  不应包含第三方实现细节，也不应把工具 schema 写死在这里。

- **`src/services/`**：服务层（流程/状态/工程细节）  
  负责“怎么做得稳”：缓存、重试、超时、子进程、证书、代理、IO 安全等。  
  通常会被 tools 调用。

- **`src/tools/`**：Tools 层（模型可调用的能力边界）  
  负责“怎么暴露给模型”：`BaseTool`/`StructuredTool` 的 name/description/args/return shape。  
  Tools 内应尽量薄，业务逻辑下沉到 services/utils。

- **`src/plugins/`**：可插拔功能层（可选能力）  
  负责“是否启用”：按环境变量/配置决定是否提供某个 tool 或某个能力入口。

- **`src/integrations/`**：第三方集成实现层（可替换供应商细节）  
  负责“对接某个具体外部系统/SDK/MCP server”的实现细节；由 plugins/tools 调用。

- **`src/utils/`**：通用小模块  
  纯函数/小封装/轻依赖（例如证书 PEM 提取、env 生成脚本、skills registry 等）。

- **`scripts/`**：可执行入口  
  只做 CLI 包装/参数解析/退出码；依赖方向只能是 `scripts/ -> src/*`。

---

## 2) Tools 规范：注册表模式（不要写死在 Agent core）

### 原则
- Tools 是模型侧 API：**schema 要稳定**（name/args/return shape）。
- Tools 应当“薄封装”：把流程、集成、工程细节放到 `services/` 或 `integrations/`。
- Tools 的来源应统一管理：不要在 `core` 里散落注册逻辑。

### 本项目落地（注册表模式）
- **本地 tools 定义**：`src/tools/local_tools.py`
  - 负责本地工具的 `StructuredTool.from_function(...)` 定义
  - 也承载“会话相关工具”（例如 export tool）的构建函数
- **统一注册入口**：`src/tools/tool_registry.py`
  - `build_tools_bundle(...)` 统一汇总：
    - `extra_tools`（例如 session export tool）
    - MCP tools（可开关）
    - local tools（含可选插件工具）
  - 统一做 **去重**、并返回 `mcp_loaded` 等运行状态
- `src/core/agent.py` 只消费 registry 的结果，不再写死 tools。

---

## 3) 可插拔能力规范：把“额外功能”做成 optional tool/provider

### 原则
- “不可替代核心能力”应留在 `core/tools/services` 的主路径里。
- “可插拔额外功能”应做到：
  - 缺少配置/依赖时 **不影响核心运行**
  - 是否启用由 env/settings 控制
  - 对 core 的依赖是单向、可选的（lazy import / try-import）

### 本项目示例：天气
- **插件入口**：`src/plugins/weather.py`
  - 提供 `build_weather_tool()`，当缺少 `AMAP_KEY` 时返回 `None`（不注册）
- **集成实现**：`src/integrations/amap_weather_mcp.py`
  - 放第三方实现细节（httpx/证书/代理/MCP 调用等）
- Tool registry 只负责“有则注册”，核心不强依赖天气能力。

---

## 4) MCP 规范：把 MCP tools 当作“tools provider”

### 原则
- MCP tools 是 tools 的一个来源（provider），本地 tools 是另一个来源。
- Core 不应感知 MCP 的实现细节，只感知“可用 tools 列表”。
- 要保证：MCP 不可用时，本地工具调用链路仍可运行。

### 本项目的细节优化（配置收敛）
已将 MCP 的关键细节收敛到 `Settings`（来自环境变量）：
- **`MCP_ENABLE`**：是否启用 MCP tools（默认启用）
- **`MCP_TOOLS_TTL_S`**：tools list 缓存 TTL（默认 60s）
- **`MCP_PYTHON`**：MCP 子进程 python 路径（可选）

对应实现：
- `src/services/mcp_client.py` 支持从 settings 读取 TTL/python
- `src/tools/mcp_tools.py` 需要显式传 `settings`
- `src/tools/tool_registry.py` 在 registry 中尊重 `settings.mcp_enable`

---

## 5) 链路表达规范（LCEL）改造：建议“计划 + 渐进式迁移”

### 原则
- 优先把“提示词 + 模型 + 解析/后处理”表达为可组合 runnable（LCEL），便于测试与插桩。
- 工具调用循环可以先保持可用，但应持续把核心步骤拆成可测单元。
- 如果未来要做更复杂的 agent 编排，建议迁移到 LangGraph（但不是现在的必要条件）。

### 推荐渐进路线（不破坏现有功能）
- **阶段 1**：把 messages 构建、system prompt、tool 执行与回填拆出为独立函数/模块（保持现有行为不变）
- **阶段 2**：把“生成 -> 工具调用 -> 回填 -> 再生成”的过程抽象为 runnable（便于 tracing/回放）
- **阶段 3（可选）**：迁移到 LangGraph，获得更清晰的状态机与可观测性

---

## 6) 依赖方向总则（防止架构腐化）
- **`core` 不依赖第三方实现细节**（这些放 `integrations/services`）
- **`tools` 依赖 `services/integrations/utils`，但尽量薄**
- **`plugins` 只做“可选启用与组合”**
- **`scripts` 只依赖 `src/*`，`src/*` 不反向依赖 `scripts`**

