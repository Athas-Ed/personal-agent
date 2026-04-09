## skills 自动整理与注册（本项目方案）

### 你的目标（总结）
- 你会**手动把 skill 文件夹粘贴到本项目根目录 `skills/`**
- 系统应当自动/半自动做到：
  - 扫描新增 skill
  - 校验 `SKILL.md` 元数据（frontmatter）
  - 生成“注册表/索引”（registry），供 UI/Agent/skill 管理工具使用

---

## 本项目实现（推荐）
本项目提供一个通用扫描脚本：
- `scripts/sync_skills.py`

它做的事：
1) 扫描 `skills/*/SKILL.md`
2) 解析 YAML frontmatter（最小字段：`name`、`description`；可选：`aliases`）
3) 发现 `scripts/*.py` 并记录
4) 输出 `skills/registry.json`

运行方式：

```bat
venv\Scripts\python scripts\sync_skills.py
```

如果某个 skill 不符合规范（缺 SKILL.md / 缺 frontmatter），脚本会在终端输出 WARN，并返回非 0 状态码。

---

## “自动触发”的方式
### 方式 A：作为开发习惯（最简单）
你每次粘贴/更新 skills 后跑一次 `scripts/sync_skills.py`。

### 方式 B：在 Streamlit UI 里加一个“刷新技能索引”按钮
适合不想切终端的场景（后续可以在 `src/ui` 做一个按钮）。

### 方式 C：作为 Git hook（pre-commit）
如果你未来把 skills 也纳入版本管理，可以用 hook 自动生成 registry。
（你当前不一定需要。）

---

## LangChain 是否有“自动注册 skills”功能？
结论：**LangChain 的 Skills（DeepAgent Skills）更多是“按需加载指令与资源”，不是替你生成 registry.json 的“资产注册器”。**

你仍然需要：
- 一个本地的“索引/注册”机制（我们现在用 `skills/registry.json`）
- 或者引入 B 方案（skillkit）来做更完整的技能管理/同步/转换

在你计划的路线（A→B→D→C）里：
- 现在先用 `scripts/sync_skills.py` 足够
- 等你要跨项目/跨平台复用时，再考虑 skillkit 来替代或增强 registry 管理

