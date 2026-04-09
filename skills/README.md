## Skills 目录说明（DeepAgent Skills / SKILL.md）

本目录用于存放可复用的“技能包”（skill）。每个 skill 是一个独立文件夹，至少包含：
- `SKILL.md`：技能说明与执行流程（包含 YAML frontmatter）
- `scripts/`：可选，确定性脚本/入口（Python 等）
- `reference/`：可选，参考资料

---

## 目录结构规范

建议结构：

```text
skills/
  <skill_name>/
    SKILL.md
    scripts/
      run.py
      ...
```

其中 `<skill_name>` 只用小写字母、数字、`-`，例如：
- `version-control`
- `outline-writer`
- `excel-export`

---

## SKILL.md 最小模板

```markdown
---
name: my-skill
aliases: 别名1, 别名2
description: 一句话描述它解决什么问题，何时应触发。
---

# 技能标题

## 适用场景
- ...

## 核心流程
1. ...
2. ...

## 工具依赖
- ...

## 注意事项
- ...
```

---

## 运行 scripts 的建议
- skills 下的脚本应尽量做到：
  - **输入/输出清晰**（CLI 参数或读取固定路径）
  - **不依赖全局状态**（除非明确依赖 `.env` / `data/`）
  - **可测试**（核心逻辑可 import 调用）

例如：

```bash
venv\\Scripts\\python skills\\excel_export\\scripts\\run.py --help
```

---

## 与本项目分层的关系（建议）
- **skills**：存“方法/流程/规范”（Prompt + 操作步骤 + 边界条件）
- **src/tools**：存“原子工具”（可被 Agent 调用的函数）
- **src/services**：封装外部系统（MCP/DB/第三方 API）
- **src/utils**：同步桥、env/代理/证书治理、缓存等

