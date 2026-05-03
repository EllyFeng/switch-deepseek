#!/usr/bin/env python3
import json
import os
import re
from pathlib import Path
from flask import Flask, jsonify, send_from_directory

# ─── Constants ────────────────────────────────────────────────────────────────
DEEPSEEK_BASE_URL = "https://api.deepseek.com"
DEEPSEEK_MODEL    = "deepseek-v4-pro"
AUTH_FIELD        = "ANTHROPIC_API_KEY"

SETTINGS_FILE = Path.home() / ".claude" / "settings.json"
BACKUP_FILE   = Path.home() / ".claude" / "settings.json.deepseek-switch.backup"
SCRIPT_DIR    = Path(__file__).parent.resolve()

# ─── Custom exception (replaces sys.exit in CLI version) ──────────────────────
class SwitchError(Exception):
    pass

# ─── Core helpers ─────────────────────────────────────────────────────────────
def load_json(path):
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, dict):
            raise SwitchError(f"文件根节点不是 JSON 对象：{path}")
        return data
    except json.JSONDecodeError as e:
        raise SwitchError(f"JSON 解析失败：{path} — {e}")
    except OSError as e:
        raise SwitchError(f"文件读取失败：{path} — {e}")

def safe_write(data, target):
    tmp = target.parent / f"settings.json.tmp.{os.getpid()}"
    try:
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
            f.write("\n")
        os.replace(tmp, target)
    except OSError as e:
        try:
            tmp.unlink()
        except OSError:
            pass
        raise SwitchError(f"写入失败：{target} — {e}")

def load_api_key():
    """Returns (key_value, source_message). No interactive prompt — web context."""
    key = os.environ.get("DEEPSEEK_API_KEY", "").strip()
    if key:
        return key, "从环境变量 DEEPSEEK_API_KEY 读取密钥。"
    env_file = SCRIPT_DIR / ".env"
    if env_file.exists():
        with open(env_file, "r", encoding="utf-8") as f:
            for line in f:
                m = re.match(r'^DEEPSEEK_API_KEY=(.+)$', line.strip())
                if m:
                    return m.group(1).strip(), f"从 {env_file.name} 读取密钥。"
        raise SwitchError(f"在 {env_file.name} 中未找到 DEEPSEEK_API_KEY 字段。")
    raise SwitchError(
        "未找到 DEEPSEEK_API_KEY。"
        "请在脚本目录创建 .env 文件并写入 DEEPSEEK_API_KEY=<your-key>，"
        "或设置同名环境变量。"
    )

# ─── Business logic ───────────────────────────────────────────────────────────
def get_status():
    settings_exists = SETTINGS_FILE.exists()
    backup_exists   = BACKUP_FILE.exists()

    if not settings_exists:
        return {
            "settings_exists": False,
            "backup_exists": backup_exists,
            "state": "unknown",
            "fields": {}
        }

    cfg = load_json(SETTINGS_FILE)
    env = cfg.get("env") or {}
    if not isinstance(env, dict):
        env = {}

    def masked(val):
        return "set" if val else "not set"

    base_url  = env.get("ANTHROPIC_BASE_URL", "")
    model     = env.get("ANTHROPIC_MODEL", "")
    haiku     = env.get("ANTHROPIC_DEFAULT_HAIKU_MODEL", "")
    sonnet    = env.get("ANTHROPIC_DEFAULT_SONNET_MODEL", "")
    opus_m    = env.get("ANTHROPIC_DEFAULT_OPUS_MODEL", "")
    auth_tok  = masked(env.get("ANTHROPIC_AUTH_TOKEN", ""))
    api_key   = masked(env.get("ANTHROPIC_API_KEY", ""))
    top_model = cfg.get("model", "")

    if base_url == DEEPSEEK_BASE_URL and model == DEEPSEEK_MODEL:
        state = "deepseek-like"
    elif not base_url and not model:
        # No custom provider configured → Claude Code using Anthropic defaults
        state = "claude-like"
    elif "claude" in model.lower() and ("anthropic" in base_url.lower() or not base_url):
        state = "claude-like"
    else:
        state = "unknown"

    return {
        "settings_exists": True,
        "backup_exists": backup_exists,
        "state": state,
        "fields": {
            "base_url":   base_url,
            "model":      model,
            "haiku":      haiku,
            "sonnet":     sonnet,
            "opus":       opus_m,
            "auth_token": auth_tok,
            "api_key":    api_key,
            "top_model":  top_model,
        }
    }

def do_switch():
    messages = []

    if not SETTINGS_FILE.exists():
        raise SwitchError(f"配置文件不存在：{SETTINGS_FILE}")
    if not os.access(SETTINGS_FILE, os.R_OK):
        raise SwitchError(f"配置文件不可读：{SETTINGS_FILE}")

    cfg = load_json(SETTINGS_FILE)

    if "env" in cfg and not isinstance(cfg["env"], dict):
        raise SwitchError(f"env 字段存在但不是 JSON 对象，中止操作。")

    env = cfg.get("env", {})
    if env.get("ANTHROPIC_BASE_URL") == DEEPSEEK_BASE_URL and \
       env.get("ANTHROPIC_MODEL") == DEEPSEEK_MODEL:
        messages.append({"level": "WARN", "text": "当前配置已是 DeepSeek，仍继续执行。"})

    if BACKUP_FILE.exists():
        messages.append({"level": "WARN", "text": f"备份已存在，跳过创建：{BACKUP_FILE.name}"})
    else:
        try:
            BACKUP_FILE.write_bytes(SETTINGS_FILE.read_bytes())
            messages.append({"level": "INFO", "text": f"备份已创建：{BACKUP_FILE.name}"})
        except OSError as e:
            raise SwitchError(f"创建备份失败：{e}")

    api_key_value, key_msg = load_api_key()
    messages.append({"level": "INFO", "text": key_msg})

    cfg.setdefault("env", {})
    cfg["env"]["ANTHROPIC_BASE_URL"] = DEEPSEEK_BASE_URL
    cfg["env"]["ANTHROPIC_MODEL"]    = DEEPSEEK_MODEL
    cfg["env"][AUTH_FIELD]           = api_key_value

    safe_write(cfg, SETTINGS_FILE)

    messages.append({"level": "INFO", "text": "切换完成。"})
    messages.append({"level": "INFO", "text": f"BASE_URL → {DEEPSEEK_BASE_URL}"})
    messages.append({"level": "INFO", "text": f"MODEL    → {DEEPSEEK_MODEL}"})
    messages.append({"level": "INFO", "text": f"API_KEY  → (已写入，未展示明文)"})
    return messages

def do_restore():
    messages = []

    if not BACKUP_FILE.exists():
        raise SwitchError(f"备份文件不存在：{BACKUP_FILE.name}。请先执行 switch。")
    if not os.access(BACKUP_FILE, os.R_OK):
        raise SwitchError(f"备份文件不可读：{BACKUP_FILE.name}")

    load_json(BACKUP_FILE)  # 验证 JSON 合法性，失败则抛 SwitchError

    safe_write(load_json(BACKUP_FILE), SETTINGS_FILE)

    messages.append({"level": "INFO", "text": "还原完成。"})
    messages.append({"level": "INFO", "text": f"已从备份恢复：{BACKUP_FILE.name}"})
    messages.append({"level": "INFO", "text": f"目标文件：{SETTINGS_FILE}"})
    return messages

# ─── Flask app ────────────────────────────────────────────────────────────────
app = Flask(__name__)

@app.route("/")
def index():
    return send_from_directory(str(SCRIPT_DIR), "index.html")

@app.route("/api/status")
def api_status():
    try:
        return jsonify(get_status())
    except SwitchError as e:
        return jsonify({"error": str(e)}), 500

@app.route("/api/switch", methods=["POST"])
def api_switch():
    try:
        messages = do_switch()
        return jsonify({"ok": True, "messages": messages})
    except SwitchError as e:
        return jsonify({"ok": False, "error": str(e)}), 400

@app.route("/api/restore", methods=["POST"])
def api_restore():
    try:
        messages = do_restore()
        return jsonify({"ok": True, "messages": messages})
    except SwitchError as e:
        return jsonify({"ok": False, "error": str(e)}), 400

# ─── Entry point ──────────────────────────────────────────────────────────────
if __name__ == "__main__":
    print("=" * 50)
    print("  Claude Code Provider 切换器")
    print("=" * 50)
    print(f"  访问地址  : http://127.0.0.1:8080")
    print(f"  配置文件  : {SETTINGS_FILE}")
    print(f"  备份文件  : {BACKUP_FILE}")
    print(f"  脚本目录  : {SCRIPT_DIR}")
    print("=" * 50)
    app.run(host="127.0.0.1", port=8080, debug=False)
