"""Tests for proxy configuration and injection."""

import pytest

from firemd.config import (
    clear_proxy_config,
    load_proxy_url,
    parse_proxy_url,
    save_proxy_url,
)
from firemd.server import ServerManager


class TestParseProxyUrl:
    """Tests for parse_proxy_url."""

    def test_full_url_with_auth(self):
        parts = parse_proxy_url("http://user:pass@proxy.com:8080")
        assert parts == {
            "host": "proxy.com",
            "port": "8080",
            "username": "user",
            "password": "pass",
        }

    def test_url_without_auth(self):
        parts = parse_proxy_url("http://proxy.com:8080")
        assert parts["host"] == "proxy.com"
        assert parts["port"] == "8080"
        assert parts["username"] == ""
        assert parts["password"] == ""

    def test_url_without_port(self):
        parts = parse_proxy_url("http://proxy.com")
        assert parts["host"] == "proxy.com"
        assert parts["port"] == ""

    def test_decodes_url_encoded_credentials(self):
        parts = parse_proxy_url("http://us%40er:p%3Ass@proxy.com:1")
        assert parts["username"] == "us@er"
        assert parts["password"] == "p:ss"

    def test_invalid_url_raises(self):
        with pytest.raises(ValueError, match="no host"):
            parse_proxy_url("not-a-url")

    def test_empty_host_raises(self):
        with pytest.raises(ValueError, match="no host"):
            parse_proxy_url("http://:8080")


class TestLoadProxyUrl:
    """Tests for load_proxy_url."""

    def test_missing_file_returns_empty(self, tmp_path, monkeypatch):
        monkeypatch.setattr(
            "firemd.config.get_config_dir", lambda: tmp_path / "nope"
        )
        assert load_proxy_url() == ""

    def test_reads_url(self, tmp_path, monkeypatch):
        monkeypatch.setattr("firemd.config.get_config_dir", lambda: tmp_path)
        (tmp_path / ".env").write_text(
            "PROXY_URL=http://user:pass@proxy.com:8080\n"
        )
        assert load_proxy_url() == "http://user:pass@proxy.com:8080"

    def test_ignores_comments_and_blanks(self, tmp_path, monkeypatch):
        monkeypatch.setattr("firemd.config.get_config_dir", lambda: tmp_path)
        (tmp_path / ".env").write_text(
            "# comment\n\nPROXY_URL=http://h:1\n"
        )
        assert load_proxy_url() == "http://h:1"

    def test_empty_file_returns_empty(self, tmp_path, monkeypatch):
        monkeypatch.setattr("firemd.config.get_config_dir", lambda: tmp_path)
        (tmp_path / ".env").write_text("")
        assert load_proxy_url() == ""


class TestSaveProxyUrl:
    """Tests for save_proxy_url."""

    def test_creates_dir_and_file(self, tmp_path, monkeypatch):
        config_dir = tmp_path / "sub" / "dir"
        monkeypatch.setattr(
            "firemd.config.get_config_dir", lambda: config_dir
        )
        result = save_proxy_url("http://user:pass@proxy.com:8080")
        assert result.exists()
        assert "PROXY_URL=http://user:pass@proxy.com:8080" in result.read_text()

    def test_overwrites_existing(self, tmp_path, monkeypatch):
        monkeypatch.setattr("firemd.config.get_config_dir", lambda: tmp_path)
        (tmp_path / ".env").write_text("PROXY_URL=http://old:1\n")
        save_proxy_url("http://new:2")
        assert load_proxy_url() == "http://new:2"


class TestClearProxyConfig:
    """Tests for clear_proxy_config."""

    def test_removes_existing(self, tmp_path, monkeypatch):
        monkeypatch.setattr("firemd.config.get_config_dir", lambda: tmp_path)
        (tmp_path / ".env").write_text("PROXY_URL=http://h:1\n")
        assert clear_proxy_config() is True
        assert not (tmp_path / ".env").exists()

    def test_returns_false_if_missing(self, tmp_path, monkeypatch):
        monkeypatch.setattr("firemd.config.get_config_dir", lambda: tmp_path)
        assert clear_proxy_config() is False


class TestProxyInjection:
    """Tests for proxy injection into Firecrawl .env content."""

    def test_injects_proxy_values(self, monkeypatch):
        monkeypatch.setattr(
            "firemd.server.load_proxy_url",
            lambda: "http://user:pass@proxy.com:8080",
        )
        monkeypatch.setattr(
            "firemd.server.parse_proxy_url",
            lambda url: {
                "host": "proxy.com", "port": "8080",
                "username": "user", "password": "pass",
            },
        )

        env_content = (
            "SOME_KEY=val\n"
            "PROXY_SERVER=\n"
            "PROXY_USERNAME=\n"
            "PROXY_PASSWORD=\n"
            "OTHER_KEY=val2\n"
        )
        result = ServerManager._inject_proxy(env_content)
        assert "PROXY_SERVER=http://user:pass@proxy.com:8080" in result
        assert "PROXY_USERNAME=user" in result
        assert "PROXY_PASSWORD=pass" in result
        assert "SOME_KEY=val" in result
        assert "OTHER_KEY=val2" in result

    def test_no_proxy_leaves_content_unchanged(self, monkeypatch):
        monkeypatch.setattr("firemd.server.load_proxy_url", lambda: "")

        env_content = (
            "PROXY_SERVER=\nPROXY_USERNAME=\nPROXY_PASSWORD=\n"
        )
        result = ServerManager._inject_proxy(env_content)
        assert result == env_content

    def test_does_not_replace_nonempty_values(self, monkeypatch):
        monkeypatch.setattr(
            "firemd.server.load_proxy_url",
            lambda: "http://user:pass@proxy.com:8080",
        )
        monkeypatch.setattr(
            "firemd.server.parse_proxy_url",
            lambda url: {
                "host": "proxy.com", "port": "8080",
                "username": "user", "password": "pass",
            },
        )

        env_content = (
            "PROXY_SERVER=http://existing\n"
            "PROXY_USERNAME=existing_user\n"
            "PROXY_PASSWORD=existing_pass\n"
        )
        result = ServerManager._inject_proxy(env_content)
        assert "PROXY_SERVER=http://existing" in result
        assert "PROXY_USERNAME=existing_user" in result
        assert "PROXY_PASSWORD=existing_pass" in result
