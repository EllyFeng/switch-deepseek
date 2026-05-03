#!/usr/bin/env bash
set -euo pipefail

# ─── Constants ─────────────────────────────────────────────────────────────────
readonly DEEPSEEK_BASE_URL="https://api.deepseek.com"
readonly DEEPSEEK_MODEL="deepseek-v4-pro"
readonly AUTH_FIELD="ANTHROPIC_API_KEY"

readonly SETTINGS_FILE="$HOME/.claude/settings.json"
readonly BACKUP_FILE="$HOME/.claude/settings.json.deepseek-switch.backup"

# ─── Helpers ───────────────────────────────────────────────────────────────────
die()  { echo "ERROR: $*" >&2; exit 1; }
warn() { echo "WARN:  $*" >&2; }
info() { echo "INFO:  $*"; }

check_jq() {
    command -v jq >/dev/null 2>&1 \
        || die "jq is required but not installed. Install: https://jqlang.github.io/jq/download/"
}

# ─── status ────────────────────────────────────────────────────────────────────
cmd_status() {
    local settings_exists backup_exists
    settings_exists="$([[ -f "$SETTINGS_FILE" ]] && echo yes || echo no)"
    backup_exists="$([[ -f "$BACKUP_FILE" ]] && echo yes || echo no)"

    echo "=== Claude Code Provider Status ==="
    echo ""
    printf "Config : %s\n" "$SETTINGS_FILE"
    printf "         exists: %s\n" "$settings_exists"
    printf "Backup : %s\n" "$BACKUP_FILE"
    printf "         exists: %s\n" "$backup_exists"
    echo ""

    if [[ "$settings_exists" == "no" ]]; then
        echo "State  : unknown  (config file not found)"
        return 0
    fi

    if ! jq -e 'type == "object"' "$SETTINGS_FILE" >/dev/null 2>&1; then
        echo "State  : unknown  (config file is not a valid JSON object)"
        return 0
    fi

    local base_url model haiku sonnet opus auth_token api_key top_model
    base_url=$(jq -r  '.env.ANTHROPIC_BASE_URL              // ""' "$SETTINGS_FILE")
    model=$(jq -r     '.env.ANTHROPIC_MODEL                 // ""' "$SETTINGS_FILE")
    haiku=$(jq -r     '.env.ANTHROPIC_DEFAULT_HAIKU_MODEL   // ""' "$SETTINGS_FILE")
    sonnet=$(jq -r    '.env.ANTHROPIC_DEFAULT_SONNET_MODEL  // ""' "$SETTINGS_FILE")
    opus=$(jq -r      '.env.ANTHROPIC_DEFAULT_OPUS_MODEL    // ""' "$SETTINGS_FILE")
    auth_token=$(jq -r 'if (.env.ANTHROPIC_AUTH_TOKEN | (. != null and . != "")) then "set" else "not set" end' "$SETTINGS_FILE")
    api_key=$(jq -r    'if (.env.ANTHROPIC_API_KEY    | (. != null and . != "")) then "set" else "not set" end' "$SETTINGS_FILE")
    top_model=$(jq -r  '.model // ""' "$SETTINGS_FILE")

    echo "Field Summary:"
    printf "  ANTHROPIC_BASE_URL             : %s\n" "${base_url:-(not set)}"
    printf "  ANTHROPIC_MODEL                : %s\n" "${model:-(not set)}"
    printf "  ANTHROPIC_DEFAULT_HAIKU_MODEL  : %s\n" "${haiku:-(not set)}"
    printf "  ANTHROPIC_DEFAULT_SONNET_MODEL : %s\n" "${sonnet:-(not set)}"
    printf "  ANTHROPIC_DEFAULT_OPUS_MODEL   : %s\n" "${opus:-(not set)}"
    printf "  ANTHROPIC_AUTH_TOKEN           : %s\n" "$auth_token"
    printf "  ANTHROPIC_API_KEY              : %s\n" "$api_key"
    printf "  model (top-level)              : %s\n" "${top_model:-(not set)}"
    echo ""

    local state="unknown"
    if [[ "$base_url" == "$DEEPSEEK_BASE_URL" && "$model" == "$DEEPSEEK_MODEL" ]]; then
        state="deepseek-like"
    elif echo "$model" | grep -qi "claude" 2>/dev/null; then
        if [[ -z "$base_url" ]] || echo "$base_url" | grep -qi "anthropic" 2>/dev/null; then
            state="claude-like"
        fi
    fi

    printf "State  : %s\n" "$state"
}

# ─── switch ────────────────────────────────────────────────────────────────────
cmd_switch() {
    check_jq

    [[ -f "$SETTINGS_FILE" ]] || die "Config file not found: $SETTINGS_FILE"
    [[ -r "$SETTINGS_FILE" ]] || die "Config file not readable: $SETTINGS_FILE"
    jq -e 'type == "object"' "$SETTINGS_FILE" >/dev/null 2>&1 \
        || die "Config file is not a valid JSON object: $SETTINGS_FILE"

    local env_type
    env_type=$(jq -r 'if has("env") then (.env | type) else "absent" end' "$SETTINGS_FILE")
    if [[ "$env_type" != "absent" && "$env_type" != "object" ]]; then
        die "Field 'env' exists but is not a JSON object (type: $env_type): $SETTINGS_FILE"
    fi

    local cur_url cur_model
    cur_url=$(jq -r '.env.ANTHROPIC_BASE_URL // ""' "$SETTINGS_FILE")
    cur_model=$(jq -r '.env.ANTHROPIC_MODEL  // ""' "$SETTINGS_FILE")
    if [[ "$cur_url" == "$DEEPSEEK_BASE_URL" && "$cur_model" == "$DEEPSEEK_MODEL" ]]; then
        warn "Config already looks like DeepSeek. Continuing anyway."
    fi

    if [[ -f "$BACKUP_FILE" ]]; then
        warn "Backup already exists at $(basename "$BACKUP_FILE") — skipping backup creation."
    else
        cp "$SETTINGS_FILE" "$BACKUP_FILE" || die "Failed to create backup: $BACKUP_FILE"
        info "Backup created: $BACKUP_FILE"
    fi

    local api_key_value
    local script_dir
    script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
    local env_file="$script_dir/.env"

    if [[ -n "${DEEPSEEK_API_KEY:-}" ]]; then
        api_key_value="$DEEPSEEK_API_KEY"
        info "Using API key from environment variable DEEPSEEK_API_KEY."
    elif [[ -f "$env_file" ]]; then
        api_key_value=$(grep -m1 '^DEEPSEEK_API_KEY=' "$env_file" | cut -d= -f2-)
        [[ -n "$api_key_value" ]] || die "DEEPSEEK_API_KEY not found or empty in $env_file"
        info "Using API key from $env_file"
    else
        printf "Enter your DeepSeek API key: "
        read -rs api_key_value
        echo ""
        [[ -n "$api_key_value" ]] || die "API key cannot be empty."
    fi

    local tmp_file
    tmp_file="$(dirname "$SETTINGS_FILE")/settings.json.tmp.$$"

    jq --arg url   "$DEEPSEEK_BASE_URL" \
       --arg model "$DEEPSEEK_MODEL"    \
       --arg key   "$api_key_value"     \
       --arg field "$AUTH_FIELD"        \
       '.env //= {} | .env.ANTHROPIC_BASE_URL = $url | .env.ANTHROPIC_MODEL = $model | .env[$field] = $key' \
       "$SETTINGS_FILE" > "$tmp_file" \
       || { rm -f "$tmp_file"; die "jq patch failed"; }

    mv "$tmp_file" "$SETTINGS_FILE" \
       || { rm -f "$tmp_file"; die "Failed to replace config file: $SETTINGS_FILE"; }

    info "Switch complete."
    info "Config  : $SETTINGS_FILE"
    info "BASE_URL: $DEEPSEEK_BASE_URL"
    info "MODEL   : $DEEPSEEK_MODEL"
    info "API_KEY : (set)"
}

# ─── restore ───────────────────────────────────────────────────────────────────
cmd_restore() {
    check_jq

    [[ -f "$BACKUP_FILE" ]] || die "Backup file not found: $BACKUP_FILE. Run 'switch' first."
    [[ -r "$BACKUP_FILE" ]] || die "Backup file not readable: $BACKUP_FILE"
    jq -e 'type == "object"' "$BACKUP_FILE" >/dev/null 2>&1 \
        || die "Backup file is not a valid JSON object: $BACKUP_FILE"

    local tmp_file
    tmp_file="$(dirname "$SETTINGS_FILE")/settings.json.tmp.$$"

    cat "$BACKUP_FILE" > "$tmp_file" \
        || { rm -f "$tmp_file"; die "Failed to read backup file: $BACKUP_FILE"; }

    mv "$tmp_file" "$SETTINGS_FILE" \
        || { rm -f "$tmp_file"; die "Failed to restore config file: $SETTINGS_FILE"; }

    info "Restore complete."
    info "Config  : $SETTINGS_FILE"
    info "Restored from: $BACKUP_FILE"
}

# ─── Entry point ───────────────────────────────────────────────────────────────
usage() {
    cat <<EOF
Usage: $(basename "$0") <command>

Commands:
  status   Show current provider status (read-only)
  switch   Switch to DeepSeek configuration
  restore  Restore original configuration from backup
EOF
    exit 1
}

case "${1:-}" in
    status)  cmd_status ;;
    switch)  cmd_switch ;;
    restore) cmd_restore ;;
    *)       usage ;;
esac
