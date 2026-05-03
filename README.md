# Claude Code Provider 切换器

一个轻量工具，用于在 Claude Code 的 Anthropic 与 DeepSeek 服务商之间快速切换。通过修补 `~/.claude/settings.json` 中的三个 `env` 字段实现，其余配置保持不变。

## 安装

```bash
# Python 版（Windows 首选，无外部依赖）
# 无需额外安装 — 仅需 Python 3.7+

# Bash 版（macOS / Linux / WSL）
# 依赖：jq ≥ 1.6
# Ubuntu/Debian:  sudo apt install jq
# macOS:          brew install jq
# 其他平台:       https://jqlang.github.io/jq/download/

# Web UI（可选）
pip install -r requirements.txt
```

## 使用

### CLI

```bash
# Python 版
python switch-deepseek.py status
python switch-deepseek.py switch
python switch-deepseek.py restore

# Bash 版
bash switch-deepseek.sh status
bash switch-deepseek.sh switch
bash switch-deepseek.sh restore
```

### Web UI

```bash
python server.py
# 然后访问 http://127.0.0.1:8080
```

## 命令说明

| 命令 | 功能 |
| --- | --- |
| `status` | 查看当前 provider 状态（只读，不暴露 key 明文） |
| `switch` | 切换到 DeepSeek 配置（自动备份原有设置） |
| `restore` | 从备份文件完整还原原始配置 |

## API Key 来源（优先级顺序）

1. `DEEPSEEK_API_KEY` 环境变量
2. 脚本同目录下的 `.env` 文件（格式：`DEEPSEEK_API_KEY=<your-key>`）
3. 交互式输入（仅 CLI；Web UI 不使用此方式）

## 工作原理

### 修改范围（白名单）

`switch` 仅修改 `~/.claude/settings.json` 中的三个字段：

- `env.ANTHROPIC_BASE_URL` → `https://api.deepseek.com`
- `env.ANTHROPIC_MODEL` → `deepseek-v4-pro`
- `env.ANTHROPIC_API_KEY` → 你的 DeepSeek API Key

所有其他字段（`statusLine`、`hooks`、`permissions`、`HTTP_PROXY`、`ANTHROPIC_DEFAULT_*`、顶层 `model` 等）保持不变。

### 写入安全

整文件 JSON 序列化，通过临时文件 + 原子 `os.replace()` 写入，不使用字符串替换。

### 备份策略

首次 `switch` 时创建单一固定备份文件 `~/.claude/settings.json.deepseek-switch.backup`。后续 `switch` 若备份已存在则跳过创建，保留切换前的原始配置。`restore` 从备份完整覆盖。

## 项目结构

```
switch-deepseek.sh      # Bash 版 CLI 实现
switch-deepseek.py      # Python 版 CLI 与核心逻辑
server.py               # Flask Web 后端
index.html              # Web 前端
mockup.html             # UI 视觉参考稿
requirements.txt        # Python 依赖（flask, pytest）
test_server.py          # 服务器测试（pytest, 80 条）
```

## 约束

- 只写 `settings.json`，不修改 `~/.claude.json`、插件或 MCP 配置
- `env` 字段不存在则自动创建；存在但非对象则报错
- 状态输出不暴露任何 key/token 值 — 仅显示 `set` 或 `not set`
