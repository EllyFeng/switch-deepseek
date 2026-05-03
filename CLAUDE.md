# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this project does

A minimal tool to switch Claude Code's provider between Anthropic and DeepSeek by patching `~/.claude/settings.json`. Two implementations exist with identical behavior:

- `switch-deepseek.py` — Python, cross-platform (primary on Windows)
- `switch-deepseek.sh` — Bash, requires `jq`

A web UI is in progress: `server.py` (Flask backend) + `index.html` (frontend), with `mockup.html` as the visual reference.

## Running the scripts

```bash
# Python version (Windows-safe)
python switch-deepseek.py status
python switch-deepseek.py switch
python switch-deepseek.py restore

# Bash version (macOS/Linux or WSL)
bash switch-deepseek.sh status
bash switch-deepseek.sh switch
bash switch-deepseek.sh restore

# Web UI (once implemented)
pip install flask
python server.py
# then open http://localhost:8080
```

## Architecture

### Core logic (`switch-deepseek.py`)

Three self-contained functions: `cmd_status`, `cmd_switch`, `cmd_restore`. They share two constants and two path variables:

- `DEEPSEEK_BASE_URL = "https://api.deepseek.com"`
- `DEEPSEEK_MODEL = "deepseek-v4-pro"`
- `SETTINGS_FILE = ~/.claude/settings.json`
- `BACKUP_FILE = ~/.claude/settings.json.deepseek-switch.backup`

`die()` calls `sys.exit(1)` — safe in CLI context, but must be replaced with a custom exception before calling these functions from a web server.

### What `switch` actually does

Reads `settings.json`, patches **only** these three fields, writes back via a temp file + atomic rename:
- `env.ANTHROPIC_BASE_URL`
- `env.ANTHROPIC_MODEL`
- `env.ANTHROPIC_API_KEY`

All other fields (`statusLine`, `hooks`, `permissions`, `env.HTTP_PROXY`, `ANTHROPIC_DEFAULT_*`, top-level `model`, etc.) must be preserved unchanged.

### API key source (priority order)

1. `DEEPSEEK_API_KEY` environment variable
2. `.env` file in the same directory as the script
3. Interactive prompt (CLI only)

### Backup strategy

Single fixed backup file. First `switch` creates it; subsequent `switch` calls skip creation if it already exists (to preserve the original pre-DeepSeek state). `restore` does a full-file overwrite from backup — no smart merge.

## Key constraints

- Only `settings.json` is ever written. Never touch `~/.claude.json`, plugins, or MCP config.
- `env` field: if absent, create it as `{}`; if present but not an object, hard-fail.
- Write safety: always construct full JSON in memory → write to `.tmp.<pid>` → `os.replace()`. Never use string/regex substitution on JSON.
- Status output must not reveal key/token values — only `"set"` or `"not set"`.
- `ANTHROPIC_DEFAULT_HAIKU/SONNET/OPUS_MODEL` and top-level `model` are explicitly read-only.

## Current `~/.claude/settings.json` state

The live config on this machine is nearly empty: `{"env": {}}`. Backup/restore will reflect this.
