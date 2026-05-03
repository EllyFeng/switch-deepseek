#!/usr/bin/env python3
import json
import os
import re
import sys
import getpass
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
sys.stderr.reconfigure(encoding="utf-8")

# ─── 常量 ──────────────────────────────────────────────────────────────────────
DEEPSEEK_BASE_URL = "https://api.deepseek.com"
DEEPSEEK_MODEL    = "deepseek-v4-pro"
AUTH_FIELD        = "ANTHROPIC_API_KEY"

SETTINGS_FILE = Path.home() / ".claude" / "settings.json"
BACKUP_FILE   = Path.home() / ".claude" / "settings.json.deepseek-switch.backup"

# ─── 工具函数 ──────────────────────────────────────────────────────────────────
def die(msg):
    print(f"ERROR: {msg}", file=sys.stderr)
    sys.exit(1)

def warn(msg):
    print(f"WARN:  {msg}", file=sys.stderr)

def info(msg):
    print(f"INFO:  {msg}")

def load_json(path):
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, dict):
            die(f"文件根节点不是 JSON 对象：{path}")
        return data
    except json.JSONDecodeError as e:
        die(f"JSON 解析失败：{path}\n       {e}")
    except OSError as e:
        die(f"文件读取失败：{path}\n       {e}")

def safe_write(data, target: Path):
    tmp = target.parent / f"settings.json.tmp.{os.getpid()}"
    try:
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
            f.write("\n")
        os.replace(tmp, target)
    except OSError as e:
        tmp.unlink(missing_ok=True)
        die(f"写入失败：{target}\n       {e}")

def load_api_key():
    # 优先读环境变量
    key = os.environ.get("DEEPSEEK_API_KEY", "")
    if key:
        info("从环境变量 DEEPSEEK_API_KEY 读取密钥。")
        return key
    # 其次读脚本同目录的 .env 文件
    env_file = Path(__file__).parent / ".env"
    if env_file.exists():
        with open(env_file, "r", encoding="utf-8") as f:
            for line in f:
                m = re.match(r'^DEEPSEEK_API_KEY=(.+)$', line.strip())
                if m:
                    key = m.group(1)
                    info(f"从 {env_file} 读取密钥。")
                    return key
        die(f"在 {env_file} 中未找到 DEEPSEEK_API_KEY")
    # 最后提示手动输入
    key = getpass.getpass("请输入 DeepSeek API Key：")
    if not key:
        die("API Key 不能为空。")
    return key

# ─── status ───────────────────────────────────────────────────────────────────
def cmd_status():
    settings_exists = SETTINGS_FILE.exists()
    backup_exists   = BACKUP_FILE.exists()

    print("=== Claude Code Provider Status ===\n")
    print(f"Config : {SETTINGS_FILE}")
    print(f"         exists: {'yes' if settings_exists else 'no'}")
    print(f"Backup : {BACKUP_FILE}")
    print(f"         exists: {'yes' if backup_exists else 'no'}\n")

    if not settings_exists:
        print("State  : unknown  (配置文件不存在)")
        return

    cfg = load_json(SETTINGS_FILE)
    env = cfg.get("env", {})

    def masked(val):
        return "set" if val else "not set"

    base_url   = env.get("ANTHROPIC_BASE_URL", "")
    model      = env.get("ANTHROPIC_MODEL", "")
    haiku      = env.get("ANTHROPIC_DEFAULT_HAIKU_MODEL", "")
    sonnet     = env.get("ANTHROPIC_DEFAULT_SONNET_MODEL", "")
    opus       = env.get("ANTHROPIC_DEFAULT_OPUS_MODEL", "")
    auth_token = masked(env.get("ANTHROPIC_AUTH_TOKEN", ""))
    api_key    = masked(env.get("ANTHROPIC_API_KEY", ""))
    top_model  = cfg.get("model", "")

    print("Field Summary:")
    print(f"  ANTHROPIC_BASE_URL             : {base_url or '(not set)'}")
    print(f"  ANTHROPIC_MODEL                : {model or '(not set)'}")
    print(f"  ANTHROPIC_DEFAULT_HAIKU_MODEL  : {haiku or '(not set)'}")
    print(f"  ANTHROPIC_DEFAULT_SONNET_MODEL : {sonnet or '(not set)'}")
    print(f"  ANTHROPIC_DEFAULT_OPUS_MODEL   : {opus or '(not set)'}")
    print(f"  ANTHROPIC_AUTH_TOKEN           : {auth_token}")
    print(f"  ANTHROPIC_API_KEY              : {api_key}")
    print(f"  model (top-level)              : {top_model or '(not set)'}\n")

    # 状态判定
    if base_url == DEEPSEEK_BASE_URL and model == DEEPSEEK_MODEL:
        state = "deepseek-like"
    elif "claude" in model.lower() and ("anthropic" in base_url.lower() or not base_url):
        state = "claude-like"
    else:
        state = "unknown"

    print(f"State  : {state}")

# ─── switch ───────────────────────────────────────────────────────────────────
def cmd_switch():
    if not SETTINGS_FILE.exists():
        die(f"配置文件不存在：{SETTINGS_FILE}")
    if not os.access(SETTINGS_FILE, os.R_OK):
        die(f"配置文件不可读：{SETTINGS_FILE}")

    cfg = load_json(SETTINGS_FILE)

    if "env" in cfg and not isinstance(cfg["env"], dict):
        die(f"env 字段存在但不是 JSON 对象：{SETTINGS_FILE}")

    # 已是 deepseek-like 则警告但继续
    env = cfg.get("env", {})
    if env.get("ANTHROPIC_BASE_URL") == DEEPSEEK_BASE_URL and \
       env.get("ANTHROPIC_MODEL") == DEEPSEEK_MODEL:
        warn("当前配置看起来已经是 DeepSeek，仍继续执行。")

    # 备份
    if BACKUP_FILE.exists():
        warn(f"备份已存在：{BACKUP_FILE.name}，跳过备份。")
    else:
        try:
            BACKUP_FILE.write_bytes(SETTINGS_FILE.read_bytes())
            info(f"备份已创建：{BACKUP_FILE}")
        except OSError as e:
            die(f"创建备份失败：{e}")

    api_key_value = load_api_key()

    # Patch 白名单字段
    cfg.setdefault("env", {})
    cfg["env"]["ANTHROPIC_BASE_URL"] = DEEPSEEK_BASE_URL
    cfg["env"]["ANTHROPIC_MODEL"]    = DEEPSEEK_MODEL
    cfg["env"][AUTH_FIELD]           = api_key_value

    safe_write(cfg, SETTINGS_FILE)

    info("切换完成。")
    info(f"Config  : {SETTINGS_FILE}")
    info(f"BASE_URL: {DEEPSEEK_BASE_URL}")
    info(f"MODEL   : {DEEPSEEK_MODEL}")
    info(f"API_KEY : (set)")

# ─── restore ──────────────────────────────────────────────────────────────────
def cmd_restore():
    if not BACKUP_FILE.exists():
        die(f"备份文件不存在：{BACKUP_FILE}。请先执行 switch。")
    if not os.access(BACKUP_FILE, os.R_OK):
        die(f"备份文件不可读：{BACKUP_FILE}")

    load_json(BACKUP_FILE)  # 验证合法性

    try:
        safe_write(load_json(BACKUP_FILE), SETTINGS_FILE)
    except SystemExit:
        raise
    except Exception as e:
        die(f"还原失败：{e}")

    info("还原完成。")
    info(f"Config  : {SETTINGS_FILE}")
    info(f"还原来源：{BACKUP_FILE}")

# ─── 入口 ──────────────────────────────────────────────────────────────────────
def usage():
    print("用法：python switch-deepseek.py <命令>\n")
    print("命令：")
    print("  status   查看当前 provider 状态（只读）")
    print("  switch   切换到 DeepSeek 配置")
    print("  restore  从备份还原原始配置")
    sys.exit(1)

if __name__ == "__main__":
    if len(sys.argv) < 2:
        usage()
    cmd = sys.argv[1]
    if cmd == "status":
        cmd_status()
    elif cmd == "switch":
        cmd_switch()
    elif cmd == "restore":
        cmd_restore()
    else:
        usage()
