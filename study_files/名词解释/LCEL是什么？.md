## LCEL 是什么？

LCEL 是 **LangChain Expression Language** 的缩写，可以理解为 LangChain 提供的一套“链路表达方式”：把提示词、模型、解析器、后处理、工具调用等步骤，都用统一的 **Runnable** 接口封装成组件，然后像“管道”一样组合成一条可执行的链路（chain）。

---

## 核心思想

- **一切皆 Runnable**：每个步骤都能用同一种方式执行（如 `invoke/ainvoke/stream/batch`）。
- **可组合**：把多个步骤按顺序拼起来，形成稳定的处理链路。
- **可观测/可插桩**：链路执行时可以注入 `config/callbacks`，用于 tracing、日志、性能分析等。
- **可测试/可替换**：每段都是独立组件，便于单测与替换（换模型、换解析器、换工具源）。

---

## 常见链路形态（概念示意）

```text
Prompt（把输入格式化成消息/文本）
→ LLM（生成）
→ Parser（把输出解析成字符串/JSON/结构化对象）
→ Postprocess（可选：清洗/截断/补充字段）
```

如果是“工具调用 agent”，链路通常会出现“循环”：

```text
构建 messages + tools
→ LLM（可能返回 tool_calls）
→ 执行工具并回填 ToolMessage
→ 再次调用 LLM
→ 直到不再请求工具 / 达到迭代上限
```

---

## LCEL 的价值（为什么要用）

- **工程化更稳**：链路结构清晰，职责边界明确。
- **更易扩展**：新增步骤（比如安全过滤、结果校验、缓存）更自然。
- **更易观测**：在链路层统一接入 callbacks，比在业务代码里到处打日志更干净。
- **更易迁移**：后续想升级到 LangGraph 这类更强的编排框架时，成本更低。

---

## 在本项目里的落地对应

你可以把本项目目前的工具调用链路理解为 LCEL 化后的几个组件组合：

- **messages 构建**：把 `system + history + user_input` 变成 `List[BaseMessage]`
- **tools 注册**：把本地 tools、MCP tools、可选插件 tools 组合成一组 tools
- **tool-calling loop**：执行“LLM → 工具 → 回填 → 再 LLM”的循环

此外我们预留了 `invoke(..., config=...)` 的入口，便于后续接入 tracing/callbacks。

