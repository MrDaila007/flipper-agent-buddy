"""Tests for pure static/class methods in bridge/daemon.py."""

import json
import pytest
from pathlib import Path

from bridge.daemon import Daemon


# ---------------------------------------------------------------------------
# _parse_skill_name
# ---------------------------------------------------------------------------

class TestParseSkillName:
    def test_valid_frontmatter(self, tmp_path):
        f = tmp_path / "SKILL.md"
        f.write_text("---\nname: commit\ndescription: Commit changes\n---\nBody text\n")
        assert Daemon._parse_skill_name(f) == "/commit"

    def test_quoted_name(self, tmp_path):
        f = tmp_path / "SKILL.md"
        f.write_text("---\nname: 'deploy'\n---\n")
        assert Daemon._parse_skill_name(f) == "/deploy"

    def test_double_quoted_name(self, tmp_path):
        f = tmp_path / "SKILL.md"
        f.write_text('---\nname: "review-pr"\n---\n')
        assert Daemon._parse_skill_name(f) == "/review-pr"

    def test_no_frontmatter_returns_none(self, tmp_path):
        f = tmp_path / "SKILL.md"
        f.write_text("Just a plain markdown file without frontmatter.\n")
        assert Daemon._parse_skill_name(f) is None

    def test_unclosed_frontmatter_returns_none(self, tmp_path):
        f = tmp_path / "SKILL.md"
        f.write_text("---\nname: broken\n")  # no closing ---
        assert Daemon._parse_skill_name(f) is None

    def test_no_name_field_returns_none(self, tmp_path):
        f = tmp_path / "SKILL.md"
        f.write_text("---\ndescription: No name here\n---\n")
        assert Daemon._parse_skill_name(f) is None

    def test_empty_name_returns_none(self, tmp_path):
        f = tmp_path / "SKILL.md"
        f.write_text("---\nname: \n---\n")
        assert Daemon._parse_skill_name(f) is None

    def test_nonexistent_file_returns_none(self, tmp_path):
        f = tmp_path / "missing.md"
        assert Daemon._parse_skill_name(f) is None


# ---------------------------------------------------------------------------
# _get_enabled_plugins
# ---------------------------------------------------------------------------

class TestGetEnabledPlugins:
    def _write_settings(self, path: Path, plugins: dict) -> None:
        path.mkdir(parents=True, exist_ok=True)
        (path / "settings.json").write_text(
            json.dumps({"enabledPlugins": plugins})
        )

    def test_single_plugin(self, tmp_path):
        self._write_settings(tmp_path, {"myPlugin@marketplace": "marketplace"})
        result = Daemon._get_enabled_plugins([tmp_path])
        assert result == {"myPlugin": "marketplace"}

    def test_multiple_plugins(self, tmp_path):
        self._write_settings(tmp_path, {
            "pluginA@mkt": "mkt",
            "pluginB@mkt": "mkt",
        })
        result = Daemon._get_enabled_plugins([tmp_path])
        assert "pluginA" in result
        assert "pluginB" in result

    def test_no_settings_file_returns_empty(self, tmp_path):
        result = Daemon._get_enabled_plugins([tmp_path])
        assert result == {}

    def test_invalid_json_returns_empty(self, tmp_path):
        (tmp_path / "settings.json").write_text("{broken}")
        result = Daemon._get_enabled_plugins([tmp_path])
        assert result == {}

    def test_null_value_skipped(self, tmp_path):
        self._write_settings(tmp_path, {"ghost@mkt": None})
        result = Daemon._get_enabled_plugins([tmp_path])
        assert result == {}

    def test_missing_at_sign_skipped(self, tmp_path):
        self._write_settings(tmp_path, {"weirdKey": "val"})
        result = Daemon._get_enabled_plugins([tmp_path])
        assert result == {}

    def test_multiple_roots_merged(self, tmp_path):
        root1 = tmp_path / "root1"
        root2 = tmp_path / "root2"
        self._write_settings(root1, {"pluginA@mkt": "mkt"})
        self._write_settings(root2, {"pluginB@mkt": "mkt"})
        result = Daemon._get_enabled_plugins([root1, root2])
        assert "pluginA" in result
        assert "pluginB" in result

    def test_first_root_wins_on_duplicate(self, tmp_path):
        root1 = tmp_path / "root1"
        root2 = tmp_path / "root2"
        self._write_settings(root1, {"plugin@mkt1": "mkt1"})
        self._write_settings(root2, {"plugin@mkt2": "mkt2"})
        result = Daemon._get_enabled_plugins([root1, root2])
        assert result["plugin"] == "mkt1"


# ---------------------------------------------------------------------------
# _read_plugin_name
# ---------------------------------------------------------------------------

class TestReadPluginName:
    def test_reads_name(self, tmp_path):
        pj = tmp_path / ".claude-plugin" / "plugin.json"
        pj.parent.mkdir(parents=True)
        pj.write_text(json.dumps({"name": "my-plugin", "version": "1.0"}))
        assert Daemon._read_plugin_name(tmp_path) == "my-plugin"

    def test_missing_plugin_json_returns_none(self, tmp_path):
        assert Daemon._read_plugin_name(tmp_path) is None

    def test_invalid_json_returns_none(self, tmp_path):
        pj = tmp_path / ".claude-plugin" / "plugin.json"
        pj.parent.mkdir(parents=True)
        pj.write_text("{bad json")
        assert Daemon._read_plugin_name(tmp_path) is None

    def test_missing_name_field_returns_none(self, tmp_path):
        pj = tmp_path / ".claude-plugin" / "plugin.json"
        pj.parent.mkdir(parents=True)
        pj.write_text(json.dumps({"version": "1.0"}))
        assert Daemon._read_plugin_name(tmp_path) is None


# ---------------------------------------------------------------------------
# _resolve_plugin_in_cache
# ---------------------------------------------------------------------------

class TestResolvePluginInCache:
    def test_returns_latest_version(self, tmp_path):
        (tmp_path / "1.0.0").mkdir()
        (tmp_path / "1.2.0").mkdir()
        (tmp_path / "0.9.0").mkdir()
        result = Daemon._resolve_plugin_in_cache(tmp_path)
        assert result.name == "1.2.0"

    def test_empty_dir_returns_none(self, tmp_path):
        assert Daemon._resolve_plugin_in_cache(tmp_path) is None

    def test_nonexistent_dir_returns_none(self, tmp_path):
        assert Daemon._resolve_plugin_in_cache(tmp_path / "missing") is None

    def test_hidden_dirs_skipped(self, tmp_path):
        (tmp_path / ".hidden").mkdir()
        assert Daemon._resolve_plugin_in_cache(tmp_path) is None

    def test_single_version(self, tmp_path):
        (tmp_path / "2.0.0").mkdir()
        result = Daemon._resolve_plugin_in_cache(tmp_path)
        assert result.name == "2.0.0"


# ---------------------------------------------------------------------------
# _resolve_plugin_in_marketplace
# ---------------------------------------------------------------------------

class TestResolvePluginInMarketplace:
    def test_finds_in_plugins_subdir(self, tmp_path):
        plugin_dir = tmp_path / "plugins" / "my-plugin"
        plugin_dir.mkdir(parents=True)
        result = Daemon._resolve_plugin_in_marketplace(tmp_path, "my-plugin")
        assert result == plugin_dir

    def test_finds_in_external_plugins_subdir(self, tmp_path):
        plugin_dir = tmp_path / "external_plugins" / "ext-plugin"
        plugin_dir.mkdir(parents=True)
        result = Daemon._resolve_plugin_in_marketplace(tmp_path, "ext-plugin")
        assert result == plugin_dir

    def test_plugins_subdir_takes_priority(self, tmp_path):
        p1 = tmp_path / "plugins" / "x"
        p2 = tmp_path / "external_plugins" / "x"
        p1.mkdir(parents=True)
        p2.mkdir(parents=True)
        result = Daemon._resolve_plugin_in_marketplace(tmp_path, "x")
        assert result == p1

    def test_finds_by_plugin_json_name(self, tmp_path):
        plugin_dir = tmp_path / "some-repo" / "my-plugin"
        pj = plugin_dir / ".claude-plugin" / "plugin.json"
        pj.parent.mkdir(parents=True)
        pj.write_text(json.dumps({"name": "my-plugin"}))
        result = Daemon._resolve_plugin_in_marketplace(tmp_path, "my-plugin")
        assert result == plugin_dir

    def test_nonexistent_mkt_dir_returns_none(self, tmp_path):
        result = Daemon._resolve_plugin_in_marketplace(tmp_path / "missing", "x")
        assert result is None

    def test_unknown_plugin_returns_none(self, tmp_path):
        result = Daemon._resolve_plugin_in_marketplace(tmp_path, "no-such-plugin")
        assert result is None
