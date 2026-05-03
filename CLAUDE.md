# CLAUDE.md

本文件为 Claude Code（claude.ai/code）在此仓库中工作时提供指引。

## 项目功能

一个轻量工具，通过修补 `~/.claude/settings.json` 来切换 Claude Code 的服务商（Anthropic ↔ DeepSeek）。提供两种行为完全相同的实现：

- `switch-deepseek.py` — Python 版，跨平台（Windows 首选）
- `switch-deepseek.sh` — Bash 版，依赖 `jq`

Web UI 正在开发中：`server.py`（Flask 后端）+ `index.html`（前端），`mockup.html` 为视觉参考稿。

## 运行脚本

```bash
# Python 版（Windows 安全）
python switch-deepseek.py status
python switch-deepseek.py switch
python switch-deepseek.py restore

# Bash 版（macOS/Linux 或 WSL）
bash switch-deepseek.sh status
bash switch-deepseek.sh switch
bash switch-deepseek.sh restore

# Web UI（实现后）
pip install flask
python server.py
# 然后访问 http://localhost:8080
```

## 架构

### 核心逻辑（`switch-deepseek.py`）

三个独立函数：`cmd_status`、`cmd_switch`、`cmd_restore`，共享两个常量和两个路径变量：

- `DEEPSEEK_BASE_URL = "https://api.deepseek.com"`
- `DEEPSEEK_MODEL = "deepseek-v4-pro"`
- `SETTINGS_FILE = ~/.claude/settings.json`
- `BACKUP_FILE = ~/.claude/settings.json.deepseek-switch.backup`

`die()` 调用 `sys.exit(1)`——在 CLI 下安全，但在从 Web 服务器调用这些函数之前必须替换为自定义异常。

### `switch` 实际做了什么

读取 `settings.json`，**仅**修补以下三个字段，通过临时文件 + 原子重命名写回：
- `env.ANTHROPIC_BASE_URL`
- `env.ANTHROPIC_MODEL`
- `env.ANTHROPIC_API_KEY`

其他所有字段（`statusLine`、`hooks`、`permissions`、`env.HTTP_PROXY`、`ANTHROPIC_DEFAULT_*`、顶层 `model` 等）必须保持不变。

### API Key 来源（优先级顺序）

1. `DEEPSEEK_API_KEY` 环境变量
2. 与脚本同目录的 `.env` 文件
3. 交互式输入（仅限 CLI）

### 备份策略

使用单一固定备份文件。首次 `switch` 时创建；后续 `switch` 若备份已存在则跳过创建（以保留切换前的原始状态）。`restore` 从备份完整覆盖文件——不做智能合并。

## 关键约束

- 只写 `settings.json`，绝不修改 `~/.claude.json`、插件或 MCP 配置。
- `env` 字段：若不存在则创建为 `{}`；若存在但不是对象则硬失败。
- 写入安全：始终在内存中构造完整 JSON → 写入 `.tmp.<pid>` → `os.replace()`，绝不对 JSON 使用字符串/正则替换。
- 状态输出不得暴露 key/token 值——只显示 `"set"` 或 `"not set"`。
- `ANTHROPIC_DEFAULT_HAIKU/SONNET/OPUS_MODEL` 和顶层 `model` 为显式只读字段。

## 当前 `~/.claude/settings.json` 状态

本机的实时配置几乎为空：`{"env": {}}`，备份/还原将反映此状态。
