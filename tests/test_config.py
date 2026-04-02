"""
Tests for config.py
"""

import json
import os
import tempfile

import pytest

from mcp_graphql_bridge.config import BridgeConfig, EndpointConfig


class TestEndpointConfig:
    def test_minimal_creation(self):
        ep = EndpointConfig(name="test", url="http://localhost:4000/graphql")
        assert ep.name == "test"
        assert ep.url == "http://localhost:4000/graphql"
        assert ep.headers == {}
        assert ep.timeout == 30.0
        assert ep.introspection_enabled is True

    def test_custom_headers(self):
        ep = EndpointConfig(
            name="secure",
            url="http://example.com/graphql",
            headers={"Authorization": "Bearer tok123"},
        )
        assert ep.headers["Authorization"] == "Bearer tok123"

    def test_env_var_expansion_in_headers(self, monkeypatch):
        monkeypatch.setenv("MY_TOKEN", "secret")
        ep = EndpointConfig(
            name="env",
            url="http://example.com/graphql",
            headers={"Authorization": "Bearer $MY_TOKEN"},
        )
        assert ep.headers["Authorization"] == "Bearer secret"

    def test_timeout_validation(self):
        with pytest.raises(Exception):
            EndpointConfig(name="t", url="http://x.com/g", timeout=0)


class TestBridgeConfig:
    def test_empty_config(self):
        cfg = BridgeConfig()
        assert cfg.endpoints == []
        assert cfg.server_name == "mcp-graphql-bridge"
        assert cfg.server_version == "0.1.0"

    def test_from_file(self):
        data = {
            "server_name": "my-server",
            "endpoints": [
                {"name": "prod", "url": "http://prod.example.com/graphql"}
            ],
        }
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".json", delete=False
        ) as fh:
            json.dump(data, fh)
            tmp_path = fh.name

        try:
            cfg = BridgeConfig.from_file(tmp_path)
            assert cfg.server_name == "my-server"
            assert len(cfg.endpoints) == 1
            assert cfg.endpoints[0].name == "prod"
        finally:
            os.unlink(tmp_path)

    def test_from_env_no_url(self, monkeypatch):
        monkeypatch.delenv("GRAPHQL_URL", raising=False)
        cfg = BridgeConfig.from_env()
        assert cfg.endpoints == []

    def test_from_env_with_url(self, monkeypatch):
        monkeypatch.setenv("GRAPHQL_URL", "http://test.example.com/graphql")
        monkeypatch.setenv(
            "GRAPHQL_HEADERS", '{"Authorization": "Bearer tok"}'
        )
        monkeypatch.setenv("GRAPHQL_TIMEOUT", "60")
        monkeypatch.setenv("MCP_SERVER_NAME", "custom-server")

        cfg = BridgeConfig.from_env()
        assert len(cfg.endpoints) == 1
        ep = cfg.endpoints[0]
        assert ep.name == "default"
        assert ep.url == "http://test.example.com/graphql"
        assert ep.headers["Authorization"] == "Bearer tok"
        assert ep.timeout == 60.0
        assert cfg.server_name == "custom-server"

    def test_from_env_invalid_headers_json(self, monkeypatch):
        monkeypatch.setenv("GRAPHQL_URL", "http://test.example.com/graphql")
        monkeypatch.setenv("GRAPHQL_HEADERS", "not-json")
        cfg = BridgeConfig.from_env()
        # Should not raise; headers default to empty dict
        assert cfg.endpoints[0].headers == {}

    def test_get_endpoint_found(self):
        cfg = BridgeConfig(
            endpoints=[
                EndpointConfig(name="alpha", url="http://a.example.com/graphql"),
                EndpointConfig(name="beta", url="http://b.example.com/graphql"),
            ]
        )
        ep = cfg.get_endpoint("alpha")
        assert ep is not None
        assert ep.url == "http://a.example.com/graphql"

    def test_get_endpoint_not_found(self):
        cfg = BridgeConfig()
        assert cfg.get_endpoint("missing") is None
