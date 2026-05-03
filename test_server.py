"""
测试套件：server.py 核心逻辑 + Flask API 路由

覆盖范围：
  - load_json / safe_write / load_api_key 工具函数
  - get_status 状态判定（含空配置回归）
  - do_switch 业务逻辑（白名单字段、备份、幂等性）
  - do_restore 业务逻辑（还原、幂等性）
  - Switch → Restore 完整生命周期
  - /api/status /api/switch /api/restore 路由（HTTP code、JSON 结构、敏感信息）
"""
import json
import os
import pytest
from pathlib import Path

import server
from server import SwitchError

# ── 测试用配置样本 ──────────────────────────────────────────────────────────────

MINIMAL_CONFIG = {"env": {}}

FULL_CLAUDE_CONFIG = {
    "model": "opus",
    "statusLine": {"command": "echo hello"},
    "hooks": {"PreToolUse": [{"matcher": "*", "hooks": []}]},
    "permissions": {"allow": ["Bash"], "deny": []},
    "env": {
        "HTTP_PROXY":  "http://proxy:8080",
        "HTTPS_PROXY": "http://proxy:8080",
        "CLAUDE_CODE_DISABLE_TERMINAL_TITLE": "1",
        "ANTHROPIC_DEFAULT_HAIKU_MODEL":  "claude-haiku-4-5",
        "ANTHROPIC_DEFAULT_SONNET_MODEL": "claude-sonnet-4-5",
        "ANTHROPIC_DEFAULT_OPUS_MODEL":   "claude-opus-4-5",
    },
}

CLAUDE_WITH_MODEL = {
    "env": {
        "ANTHROPIC_MODEL":   "claude-sonnet-4-5",
        "ANTHROPIC_API_KEY": "sk-ant-real-key",
    }
}

DEEPSEEK_CONFIG = {
    "model": "opus",
    "env": {
        "ANTHROPIC_BASE_URL": server.DEEPSEEK_BASE_URL,
        "ANTHROPIC_MODEL":    server.DEEPSEEK_MODEL,
        "ANTHROPIC_API_KEY":  "sk-deepseek-key",
        "HTTP_PROXY":         "http://proxy:8080",
    },
}

FAKE_KEY = "sk-fake-test-key-9999"


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture
def tmp_files(tmp_path):
    settings = tmp_path / "settings.json"
    backup   = tmp_path / "settings.json.deepseek-switch.backup"
    return settings, backup


@pytest.fixture
def patch_paths(tmp_files, monkeypatch):
    settings, backup = tmp_files
    monkeypatch.setattr(server, "SETTINGS_FILE", settings)
    monkeypatch.setattr(server, "BACKUP_FILE",   backup)
    return settings, backup


@pytest.fixture
def flask_client(patch_paths):
    server.app.config["TESTING"] = True
    with server.app.test_client() as client:
        yield client


def _write(path, data):
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def _read(path):
    return json.loads(path.read_text(encoding="utf-8"))


# ═══════════════════════════════════════════════════════════════════════════════
# 1. load_json
# ═══════════════════════════════════════════════════════════════════════════════

class TestLoadJson:
    def test_valid_json_object(self, tmp_path):
        f = tmp_path / "s.json"
        _write(f, {"env": {}})
        assert server.load_json(f) == {"env": {}}

    def test_missing_file_raises(self, tmp_path):
        with pytest.raises(SwitchError, match="文件读取失败"):
            server.load_json(tmp_path / "nonexistent.json")

    def test_invalid_json_raises(self, tmp_path):
        f = tmp_path / "s.json"
        f.write_text("not json {{ broken", encoding="utf-8")
        with pytest.raises(SwitchError, match="JSON 解析失败"):
            server.load_json(f)

    def test_json_array_root_raises(self, tmp_path):
        f = tmp_path / "s.json"
        f.write_text("[1, 2, 3]", encoding="utf-8")
        with pytest.raises(SwitchError, match="不是 JSON 对象"):
            server.load_json(f)

    def test_null_root_raises(self, tmp_path):
        f = tmp_path / "s.json"
        f.write_text("null", encoding="utf-8")
        with pytest.raises(SwitchError, match="不是 JSON 对象"):
            server.load_json(f)

    def test_empty_file_raises(self, tmp_path):
        f = tmp_path / "s.json"
        f.write_text("", encoding="utf-8")
        with pytest.raises(SwitchError, match="JSON 解析失败"):
            server.load_json(f)


# ═══════════════════════════════════════════════════════════════════════════════
# 2. safe_write
# ═══════════════════════════════════════════════════════════════════════════════

class TestSafeWrite:
    def test_writes_correct_content(self, tmp_path):
        target = tmp_path / "out.json"
        data = {"key": "value", "env": {"X": "1"}}
        server.safe_write(data, target)
        assert _read(target) == data

    def test_overwrites_existing_file(self, tmp_path):
        target = tmp_path / "out.json"
        _write(target, {"old": True})
        server.safe_write({"new": True}, target)
        assert _read(target) == {"new": True}

    def test_no_tmp_file_left_after_success(self, tmp_path):
        server.safe_write({"a": 1}, tmp_path / "out.json")
        assert list(tmp_path.glob("*.tmp.*")) == []

    def test_unicode_preserved(self, tmp_path):
        target = tmp_path / "out.json"
        server.safe_write({"msg": "你好世界"}, target)
        assert _read(target)["msg"] == "你好世界"

    def test_output_is_valid_json(self, tmp_path):
        target = tmp_path / "out.json"
        server.safe_write({"env": {}}, target)
        parsed = json.loads(target.read_text(encoding="utf-8"))
        assert isinstance(parsed, dict)

    def test_ends_with_newline(self, tmp_path):
        target = tmp_path / "out.json"
        server.safe_write({"a": 1}, target)
        assert target.read_text(encoding="utf-8").endswith("\n")


# ═══════════════════════════════════════════════════════════════════════════════
# 3. load_api_key
# ═══════════════════════════════════════════════════════════════════════════════

class TestLoadApiKey:
    def test_reads_from_env_var(self, monkeypatch):
        monkeypatch.setenv("DEEPSEEK_API_KEY", FAKE_KEY)
        key, msg = server.load_api_key()
        assert key == FAKE_KEY
        assert "环境变量" in msg

    def test_env_var_takes_priority_over_file(self, tmp_path, monkeypatch):
        env_file = tmp_path / ".env"
        env_file.write_text("DEEPSEEK_API_KEY=file-key\n", encoding="utf-8")
        monkeypatch.setattr(server, "SCRIPT_DIR", tmp_path)
        monkeypatch.setenv("DEEPSEEK_API_KEY", "env-key")
        key, _ = server.load_api_key()
        assert key == "env-key"

    def test_reads_from_dot_env_file(self, tmp_path, monkeypatch):
        monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
        (tmp_path / ".env").write_text(f"DEEPSEEK_API_KEY={FAKE_KEY}\n", encoding="utf-8")
        monkeypatch.setattr(server, "SCRIPT_DIR", tmp_path)
        key, msg = server.load_api_key()
        assert key == FAKE_KEY
        assert ".env" in msg

    def test_missing_key_in_env_file_raises(self, tmp_path, monkeypatch):
        monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
        (tmp_path / ".env").write_text("OTHER_VAR=123\n", encoding="utf-8")
        monkeypatch.setattr(server, "SCRIPT_DIR", tmp_path)
        with pytest.raises(SwitchError, match="未找到 DEEPSEEK_API_KEY"):
            server.load_api_key()

    def test_no_env_var_no_file_raises(self, tmp_path, monkeypatch):
        monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
        empty_dir = tmp_path / "empty"
        empty_dir.mkdir()
        monkeypatch.setattr(server, "SCRIPT_DIR", empty_dir)
        with pytest.raises(SwitchError, match="未找到 DEEPSEEK_API_KEY"):
            server.load_api_key()

    def test_key_is_stripped(self, monkeypatch):
        monkeypatch.setenv("DEEPSEEK_API_KEY", f"  {FAKE_KEY}  ")
        key, _ = server.load_api_key()
        assert key == FAKE_KEY


# ═══════════════════════════════════════════════════════════════════════════════
# 4. get_status — 状态判定
# ═══════════════════════════════════════════════════════════════════════════════

class TestGetStatus:
    def test_missing_settings_file(self, patch_paths):
        result = server.get_status()
        assert result["settings_exists"] is False
        assert result["state"] == "unknown"
        assert result["fields"] == {}

    def test_empty_config_is_claude_like(self, patch_paths):
        """回归：{"env":{}} 还原后应判为 claude-like，不是 unknown"""
        settings, _ = patch_paths
        _write(settings, MINIMAL_CONFIG)
        assert server.get_status()["state"] == "claude-like"

    def test_no_env_key_at_all_is_claude_like(self, patch_paths):
        settings, _ = patch_paths
        _write(settings, {"model": "opus"})
        assert server.get_status()["state"] == "claude-like"

    def test_deepseek_config_detected(self, patch_paths):
        settings, _ = patch_paths
        _write(settings, DEEPSEEK_CONFIG)
        assert server.get_status()["state"] == "deepseek-like"

    def test_claude_model_name_detected(self, patch_paths):
        settings, _ = patch_paths
        _write(settings, CLAUDE_WITH_MODEL)
        assert server.get_status()["state"] == "claude-like"

    def test_unknown_custom_url(self, patch_paths):
        settings, _ = patch_paths
        _write(settings, {"env": {
            "ANTHROPIC_BASE_URL": "https://other-provider.example.com",
            "ANTHROPIC_MODEL":    "some-custom-model",
        }})
        assert server.get_status()["state"] == "unknown"

    def test_deepseek_url_without_model_is_unknown(self, patch_paths):
        settings, _ = patch_paths
        _write(settings, {"env": {"ANTHROPIC_BASE_URL": server.DEEPSEEK_BASE_URL}})
        assert server.get_status()["state"] == "unknown"

    def test_backup_exists_flag_false(self, patch_paths):
        settings, _ = patch_paths
        _write(settings, MINIMAL_CONFIG)
        assert server.get_status()["backup_exists"] is False

    def test_backup_exists_flag_true(self, patch_paths):
        settings, backup = patch_paths
        _write(settings, MINIMAL_CONFIG)
        backup.write_text("{}", encoding="utf-8")
        assert server.get_status()["backup_exists"] is True

    def test_api_key_not_exposed_in_response(self, patch_paths):
        """TC-014：密钥明文绝不能出现在 status 响应中"""
        settings, _ = patch_paths
        _write(settings, {"env": {"ANTHROPIC_API_KEY": "sk-super-secret"}})
        result = server.get_status()
        assert "sk-super-secret" not in str(result)
        assert result["fields"]["api_key"] == "set"

    def test_auth_token_not_exposed(self, patch_paths):
        settings, _ = patch_paths
        _write(settings, {"env": {"ANTHROPIC_AUTH_TOKEN": "tok-super-secret"}})
        result = server.get_status()
        assert "tok-super-secret" not in str(result)
        assert result["fields"]["auth_token"] == "set"

    def test_unset_keys_show_not_set(self, patch_paths):
        settings, _ = patch_paths
        _write(settings, MINIMAL_CONFIG)
        fields = server.get_status()["fields"]
        assert fields["api_key"]    == "not set"
        assert fields["auth_token"] == "not set"

    def test_fields_contain_all_expected_keys(self, patch_paths):
        settings, _ = patch_paths
        _write(settings, FULL_CLAUDE_CONFIG)
        fields = server.get_status()["fields"]
        for key in ("base_url", "model", "haiku", "sonnet", "opus",
                    "auth_token", "api_key", "top_model"):
            assert key in fields

    def test_default_model_fields_populated(self, patch_paths):
        settings, _ = patch_paths
        _write(settings, FULL_CLAUDE_CONFIG)
        fields = server.get_status()["fields"]
        assert fields["haiku"]  == "claude-haiku-4-5"
        assert fields["sonnet"] == "claude-sonnet-4-5"
        assert fields["opus"]   == "claude-opus-4-5"

    def test_top_level_model_reported(self, patch_paths):
        settings, _ = patch_paths
        _write(settings, FULL_CLAUDE_CONFIG)
        assert server.get_status()["fields"]["top_model"] == "opus"


# ═══════════════════════════════════════════════════════════════════════════════
# 5. do_switch
# ═══════════════════════════════════════════════════════════════════════════════

class TestDoSwitch:
    def test_missing_settings_raises(self, patch_paths, monkeypatch):
        monkeypatch.setenv("DEEPSEEK_API_KEY", FAKE_KEY)
        with pytest.raises(SwitchError, match="配置文件不存在"):
            server.do_switch()

    def test_creates_backup_on_first_switch(self, patch_paths, monkeypatch):
        """TC-004：首次切换必须完整备份当前配置"""
        settings, backup = patch_paths
        _write(settings, MINIMAL_CONFIG)
        monkeypatch.setenv("DEEPSEEK_API_KEY", FAKE_KEY)
        msgs = server.do_switch()
        assert backup.exists()
        assert _read(backup) == MINIMAL_CONFIG
        assert any("备份已创建" in m["text"] for m in msgs)

    def test_backup_is_complete_not_partial(self, patch_paths, monkeypatch):
        """TC-004：备份必须是完整文件，不是只保存 env"""
        settings, backup = patch_paths
        _write(settings, FULL_CLAUDE_CONFIG)
        monkeypatch.setenv("DEEPSEEK_API_KEY", FAKE_KEY)
        server.do_switch()
        assert _read(backup) == FULL_CLAUDE_CONFIG

    def test_skips_backup_if_exists(self, patch_paths, monkeypatch):
        settings, backup = patch_paths
        _write(settings, MINIMAL_CONFIG)
        backup.write_text(json.dumps(MINIMAL_CONFIG), encoding="utf-8")
        monkeypatch.setenv("DEEPSEEK_API_KEY", FAKE_KEY)
        msgs = server.do_switch()
        assert any("跳过" in m["text"] and m["level"] == "WARN" for m in msgs)

    def test_patches_only_whitelist_fields(self, patch_paths, monkeypatch):
        """TC-005：switch 只能改白名单字段"""
        settings, _ = patch_paths
        _write(settings, FULL_CLAUDE_CONFIG)
        monkeypatch.setenv("DEEPSEEK_API_KEY", FAKE_KEY)
        server.do_switch()
        result = _read(settings)
        # 白名单字段已更新
        assert result["env"]["ANTHROPIC_BASE_URL"] == server.DEEPSEEK_BASE_URL
        assert result["env"]["ANTHROPIC_MODEL"]    == server.DEEPSEEK_MODEL
        assert result["env"]["ANTHROPIC_API_KEY"]  == FAKE_KEY
        # 其他字段原样保留
        assert result["model"]       == "opus"
        assert result["statusLine"]  == FULL_CLAUDE_CONFIG["statusLine"]
        assert result["hooks"]       == FULL_CLAUDE_CONFIG["hooks"]
        assert result["permissions"] == FULL_CLAUDE_CONFIG["permissions"]

    def test_preserves_proxy_settings(self, patch_paths, monkeypatch):
        """TC-018：代理配置不得被 switch 破坏"""
        settings, _ = patch_paths
        _write(settings, FULL_CLAUDE_CONFIG)
        monkeypatch.setenv("DEEPSEEK_API_KEY", FAKE_KEY)
        server.do_switch()
        result = _read(settings)
        assert result["env"]["HTTP_PROXY"]  == "http://proxy:8080"
        assert result["env"]["HTTPS_PROXY"] == "http://proxy:8080"

    def test_preserves_default_model_fields(self, patch_paths, monkeypatch):
        """TC-019：ANTHROPIC_DEFAULT_* 不得被 switch 改写"""
        settings, _ = patch_paths
        _write(settings, FULL_CLAUDE_CONFIG)
        monkeypatch.setenv("DEEPSEEK_API_KEY", FAKE_KEY)
        server.do_switch()
        result = _read(settings)
        assert result["env"]["ANTHROPIC_DEFAULT_HAIKU_MODEL"]  == "claude-haiku-4-5"
        assert result["env"]["ANTHROPIC_DEFAULT_SONNET_MODEL"] == "claude-sonnet-4-5"
        assert result["env"]["ANTHROPIC_DEFAULT_OPUS_MODEL"]   == "claude-opus-4-5"

    def test_top_level_model_unchanged(self, patch_paths, monkeypatch):
        """TC-020：顶层 model 字段不得被修改"""
        settings, _ = patch_paths
        _write(settings, FULL_CLAUDE_CONFIG)
        monkeypatch.setenv("DEEPSEEK_API_KEY", FAKE_KEY)
        server.do_switch()
        assert _read(settings)["model"] == "opus"

    def test_auto_creates_env_if_absent(self, patch_paths, monkeypatch):
        """TC-006：settings 没有 env 键时自动创建"""
        settings, _ = patch_paths
        _write(settings, {"model": "opus"})   # 无 env 键
        monkeypatch.setenv("DEEPSEEK_API_KEY", FAKE_KEY)
        server.do_switch()
        result = _read(settings)
        assert "env" in result
        assert result["env"]["ANTHROPIC_BASE_URL"] == server.DEEPSEEK_BASE_URL
        assert result["model"] == "opus"   # 顶层 model 保留

    def test_non_object_env_raises(self, patch_paths, monkeypatch):
        """TC-007：env 存在但非对象 → 硬失败"""
        settings, _ = patch_paths
        _write(settings, {"env": "string-value"})
        monkeypatch.setenv("DEEPSEEK_API_KEY", FAKE_KEY)
        with pytest.raises(SwitchError, match="不是 JSON 对象"):
            server.do_switch()

    def test_non_object_env_does_not_write(self, patch_paths, monkeypatch):
        """TC-007：硬失败后原文件不得被改写"""
        settings, _ = patch_paths
        original = {"env": "string-value"}
        _write(settings, original)
        monkeypatch.setenv("DEEPSEEK_API_KEY", FAKE_KEY)
        with pytest.raises(SwitchError):
            server.do_switch()
        assert _read(settings) == original

    def test_settings_json_valid_after_switch(self, patch_paths, monkeypatch):
        """TC-015：switch 后 settings.json 仍是合法 JSON"""
        settings, _ = patch_paths
        _write(settings, FULL_CLAUDE_CONFIG)
        monkeypatch.setenv("DEEPSEEK_API_KEY", FAKE_KEY)
        server.do_switch()
        parsed = json.loads(settings.read_text(encoding="utf-8"))
        assert isinstance(parsed, dict)

    def test_idempotent_switch(self, patch_paths, monkeypatch):
        """TC-009：重复执行 switch，配置结果稳定，原始备份不被覆盖"""
        settings, backup = patch_paths
        _write(settings, FULL_CLAUDE_CONFIG)
        monkeypatch.setenv("DEEPSEEK_API_KEY", FAKE_KEY)
        server.do_switch()
        after_first  = _read(settings)
        server.do_switch()
        after_second = _read(settings)
        assert after_first == after_second
        assert _read(backup) == FULL_CLAUDE_CONFIG   # 原始备份未被覆盖

    def test_warns_if_already_deepseek(self, patch_paths, monkeypatch):
        settings, backup = patch_paths
        _write(settings, DEEPSEEK_CONFIG)
        backup.write_text(json.dumps(DEEPSEEK_CONFIG), encoding="utf-8")
        monkeypatch.setenv("DEEPSEEK_API_KEY", FAKE_KEY)
        msgs = server.do_switch()
        assert any("已是 DeepSeek" in m["text"] and m["level"] == "WARN" for m in msgs)

    def test_messages_have_correct_structure(self, patch_paths, monkeypatch):
        settings, _ = patch_paths
        _write(settings, MINIMAL_CONFIG)
        monkeypatch.setenv("DEEPSEEK_API_KEY", FAKE_KEY)
        msgs = server.do_switch()
        for m in msgs:
            assert "level" in m and "text" in m
            assert m["level"] in ("INFO", "WARN", "ERROR")

    def test_api_key_not_in_messages(self, patch_paths, monkeypatch):
        """切换成功后日志不得包含密钥明文"""
        settings, _ = patch_paths
        _write(settings, MINIMAL_CONFIG)
        monkeypatch.setenv("DEEPSEEK_API_KEY", FAKE_KEY)
        msgs = server.do_switch()
        for m in msgs:
            assert FAKE_KEY not in m["text"]


# ═══════════════════════════════════════════════════════════════════════════════
# 6. do_restore
# ═══════════════════════════════════════════════════════════════════════════════

class TestDoRestore:
    def test_missing_backup_raises(self, patch_paths):
        """TC-011：无备份时 restore 必须报错"""
        settings, _ = patch_paths
        _write(settings, DEEPSEEK_CONFIG)
        with pytest.raises(SwitchError, match="备份文件不存在"):
            server.do_restore()

    def test_missing_backup_does_not_modify_settings(self, patch_paths):
        settings, _ = patch_paths
        _write(settings, DEEPSEEK_CONFIG)
        with pytest.raises(SwitchError):
            server.do_restore()
        assert _read(settings) == DEEPSEEK_CONFIG   # 未被改动

    def test_restores_full_original_config(self, patch_paths):
        """TC-010：restore 后 settings.json 与备份内容完全一致"""
        settings, backup = patch_paths
        backup.write_text(json.dumps(FULL_CLAUDE_CONFIG, ensure_ascii=False), encoding="utf-8")
        _write(settings, DEEPSEEK_CONFIG)
        server.do_restore()
        assert _read(settings) == FULL_CLAUDE_CONFIG

    def test_restored_json_is_valid(self, patch_paths):
        """TC-015：restore 后文件仍是合法 JSON"""
        settings, backup = patch_paths
        backup.write_text(json.dumps(FULL_CLAUDE_CONFIG), encoding="utf-8")
        _write(settings, DEEPSEEK_CONFIG)
        server.do_restore()
        parsed = json.loads(settings.read_text(encoding="utf-8"))
        assert isinstance(parsed, dict)

    def test_invalid_backup_json_raises(self, patch_paths):
        settings, backup = patch_paths
        _write(settings, DEEPSEEK_CONFIG)
        backup.write_text("not valid json {{", encoding="utf-8")
        with pytest.raises(SwitchError, match="JSON 解析失败"):
            server.do_restore()

    def test_invalid_backup_does_not_modify_settings(self, patch_paths):
        settings, backup = patch_paths
        _write(settings, DEEPSEEK_CONFIG)
        backup.write_text("corrupted", encoding="utf-8")
        with pytest.raises(SwitchError):
            server.do_restore()
        assert _read(settings) == DEEPSEEK_CONFIG   # 原文件未被覆盖

    def test_idempotent_restore(self, patch_paths):
        """TC-012：重复 restore 结果稳定"""
        settings, backup = patch_paths
        backup.write_text(json.dumps(FULL_CLAUDE_CONFIG), encoding="utf-8")
        _write(settings, DEEPSEEK_CONFIG)
        server.do_restore()
        first  = _read(settings)
        server.do_restore()
        second = _read(settings)
        assert first == second

    def test_restore_minimal_config(self, patch_paths):
        """回归：还原到 {"env":{}} 必须正常工作并判为 claude-like"""
        settings, backup = patch_paths
        backup.write_text(json.dumps(MINIMAL_CONFIG), encoding="utf-8")
        _write(settings, DEEPSEEK_CONFIG)
        server.do_restore()
        assert _read(settings) == MINIMAL_CONFIG
        assert server.get_status()["state"] == "claude-like"

    def test_messages_have_correct_structure(self, patch_paths):
        settings, backup = patch_paths
        backup.write_text(json.dumps(MINIMAL_CONFIG), encoding="utf-8")
        _write(settings, DEEPSEEK_CONFIG)
        msgs = server.do_restore()
        for m in msgs:
            assert "level" in m and "text" in m


# ═══════════════════════════════════════════════════════════════════════════════
# 7. Switch → Restore 完整生命周期
# ═══════════════════════════════════════════════════════════════════════════════

class TestSwitchRestoreCycle:
    def test_full_cycle_preserves_original(self, patch_paths, monkeypatch):
        """切换后还原，settings.json 必须与初始状态完全一致"""
        settings, _ = patch_paths
        _write(settings, FULL_CLAUDE_CONFIG)
        original = _read(settings)
        monkeypatch.setenv("DEEPSEEK_API_KEY", FAKE_KEY)
        server.do_switch()
        assert _read(settings) != original   # 已切换
        server.do_restore()
        assert _read(settings) == original   # 完全还原

    def test_status_reflects_each_phase(self, patch_paths, monkeypatch):
        """状态判定必须在每个阶段都正确"""
        settings, _ = patch_paths
        _write(settings, FULL_CLAUDE_CONFIG)
        assert server.get_status()["state"] == "claude-like"
        monkeypatch.setenv("DEEPSEEK_API_KEY", FAKE_KEY)
        server.do_switch()
        assert server.get_status()["state"] == "deepseek-like"
        server.do_restore()
        assert server.get_status()["state"] == "claude-like"

    def test_backup_intact_after_double_switch(self, patch_paths, monkeypatch):
        """两次切换后原始备份不得被覆盖"""
        settings, backup = patch_paths
        _write(settings, FULL_CLAUDE_CONFIG)
        monkeypatch.setenv("DEEPSEEK_API_KEY", FAKE_KEY)
        server.do_switch()
        original_backup = _read(backup)
        server.do_switch()
        assert _read(backup) == original_backup

    def test_minimal_config_full_cycle(self, patch_paths, monkeypatch):
        """本机实际场景：{"env":{}} 起点，切换后还原"""
        settings, _ = patch_paths
        _write(settings, MINIMAL_CONFIG)
        monkeypatch.setenv("DEEPSEEK_API_KEY", FAKE_KEY)
        server.do_switch()
        assert _read(settings)["env"]["ANTHROPIC_BASE_URL"] == server.DEEPSEEK_BASE_URL
        server.do_restore()
        assert _read(settings) == MINIMAL_CONFIG
        assert server.get_status()["state"] == "claude-like"


# ═══════════════════════════════════════════════════════════════════════════════
# 8. Flask 路由：/api/status
# ═══════════════════════════════════════════════════════════════════════════════

class TestApiStatus:
    def test_returns_200(self, flask_client, patch_paths):
        settings, _ = patch_paths
        _write(settings, MINIMAL_CONFIG)
        assert flask_client.get("/api/status").status_code == 200

    def test_response_structure(self, flask_client, patch_paths):
        settings, _ = patch_paths
        _write(settings, MINIMAL_CONFIG)
        data = flask_client.get("/api/status").get_json()
        for key in ("state", "settings_exists", "backup_exists", "fields"):
            assert key in data

    def test_fields_structure(self, flask_client, patch_paths):
        settings, _ = patch_paths
        _write(settings, MINIMAL_CONFIG)
        fields = flask_client.get("/api/status").get_json()["fields"]
        for key in ("base_url", "model", "api_key", "auth_token"):
            assert key in fields

    def test_state_value_is_valid(self, flask_client, patch_paths):
        settings, _ = patch_paths
        _write(settings, MINIMAL_CONFIG)
        state = flask_client.get("/api/status").get_json()["state"]
        assert state in ("claude-like", "deepseek-like", "unknown")

    def test_no_secret_in_response_body(self, flask_client, patch_paths):
        """TC-014：密钥明文不得出现在任何响应正文中"""
        settings, _ = patch_paths
        _write(settings, {
            "env": {
                "ANTHROPIC_API_KEY":    "sk-super-secret-key",
                "ANTHROPIC_AUTH_TOKEN": "tok-super-secret-token",
            }
        })
        body = flask_client.get("/api/status").get_data(as_text=True)
        assert "sk-super-secret-key"    not in body
        assert "tok-super-secret-token" not in body

    def test_missing_settings_returns_200_with_flag(self, flask_client, patch_paths):
        # settings 文件不存在时，接口应返回 200 而非 500
        data = flask_client.get("/api/status").get_json()
        assert data["settings_exists"] is False


# ═══════════════════════════════════════════════════════════════════════════════
# 9. Flask 路由：/api/switch
# ═══════════════════════════════════════════════════════════════════════════════

class TestApiSwitch:
    def test_success_returns_200_and_ok(self, flask_client, patch_paths, monkeypatch):
        settings, _ = patch_paths
        _write(settings, MINIMAL_CONFIG)
        monkeypatch.setenv("DEEPSEEK_API_KEY", FAKE_KEY)
        resp = flask_client.post("/api/switch")
        assert resp.status_code == 200
        assert resp.get_json()["ok"] is True

    def test_success_has_messages_list(self, flask_client, patch_paths, monkeypatch):
        settings, _ = patch_paths
        _write(settings, MINIMAL_CONFIG)
        monkeypatch.setenv("DEEPSEEK_API_KEY", FAKE_KEY)
        data = flask_client.post("/api/switch").get_json()
        assert isinstance(data["messages"], list)
        assert len(data["messages"]) > 0

    def test_messages_level_and_text_present(self, flask_client, patch_paths, monkeypatch):
        settings, _ = patch_paths
        _write(settings, MINIMAL_CONFIG)
        monkeypatch.setenv("DEEPSEEK_API_KEY", FAKE_KEY)
        msgs = flask_client.post("/api/switch").get_json()["messages"]
        for m in msgs:
            assert "level" in m and "text" in m
            assert m["level"] in ("INFO", "WARN", "ERROR")

    def test_missing_settings_returns_400(self, flask_client, patch_paths, monkeypatch):
        monkeypatch.setenv("DEEPSEEK_API_KEY", FAKE_KEY)
        resp = flask_client.post("/api/switch")
        assert resp.status_code == 400
        assert resp.get_json()["ok"] is False
        assert "error" in resp.get_json()

    def test_missing_api_key_returns_400(self, flask_client, patch_paths, monkeypatch, tmp_path):
        settings, _ = patch_paths
        _write(settings, MINIMAL_CONFIG)
        monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
        empty_dir = tmp_path / "no-env"
        empty_dir.mkdir()
        monkeypatch.setattr(server, "SCRIPT_DIR", empty_dir)
        resp = flask_client.post("/api/switch")
        assert resp.status_code == 400

    def test_switch_actually_writes_deepseek_url(self, flask_client, patch_paths, monkeypatch):
        settings, _ = patch_paths
        _write(settings, MINIMAL_CONFIG)
        monkeypatch.setenv("DEEPSEEK_API_KEY", FAKE_KEY)
        flask_client.post("/api/switch")
        assert _read(settings)["env"]["ANTHROPIC_BASE_URL"] == server.DEEPSEEK_BASE_URL

    def test_get_method_not_allowed(self, flask_client):
        assert flask_client.get("/api/switch").status_code == 405


# ═══════════════════════════════════════════════════════════════════════════════
# 10. Flask 路由：/api/restore
# ═══════════════════════════════════════════════════════════════════════════════

class TestApiRestore:
    def test_success_returns_200_and_ok(self, flask_client, patch_paths):
        settings, backup = patch_paths
        _write(settings, DEEPSEEK_CONFIG)
        backup.write_text(json.dumps(FULL_CLAUDE_CONFIG), encoding="utf-8")
        resp = flask_client.post("/api/restore")
        assert resp.status_code == 200
        assert resp.get_json()["ok"] is True

    def test_missing_backup_returns_400(self, flask_client, patch_paths):
        settings, _ = patch_paths
        _write(settings, DEEPSEEK_CONFIG)
        resp = flask_client.post("/api/restore")
        assert resp.status_code == 400
        assert resp.get_json()["ok"] is False

    def test_restore_actually_writes_original(self, flask_client, patch_paths):
        settings, backup = patch_paths
        _write(settings, DEEPSEEK_CONFIG)
        backup.write_text(json.dumps(FULL_CLAUDE_CONFIG), encoding="utf-8")
        flask_client.post("/api/restore")
        assert _read(settings) == FULL_CLAUDE_CONFIG

    def test_corrupt_backup_returns_400(self, flask_client, patch_paths):
        settings, backup = patch_paths
        _write(settings, DEEPSEEK_CONFIG)
        backup.write_text("not-json", encoding="utf-8")
        resp = flask_client.post("/api/restore")
        assert resp.status_code == 400

    def test_get_method_not_allowed(self, flask_client):
        assert flask_client.get("/api/restore").status_code == 405
