import os
import tempfile
from unittest import mock
import pytest
import yaml
from bin.main import generate_vector_config_from_env, validate_vector_config

MINIMAL_ENV = {
    "DEBUG": "1",
    "SOURCE_FILE_INCLUDE_PATHS": "/foo/bar.log,/bar/baz.log",
    "SINK_LOKI_ENDPOINT": "http://localhost:3100/api/v1/push",
    "SINK_LOKI_LABELS": "job=test,instance=test",
}

FULL_ENV = {
    **MINIMAL_ENV,
    "USE_JSON_FIELD_AS_TIMESTAMP": "foo",
    "SINK_LOKI_TENANT_ID": "123",
    "SINK_LOKI_AUTH_STRATEGY": "basic",
    "SINK_LOKI_AUTH_USER": "foo",
    "SINK_LOKI_AUTH_PASSWORD": "bar",
}


def _env(monkeypatch, env_dict: dict):
    with mock.patch.dict(os.environ, clear=True):
        with tempfile.TemporaryDirectory() as tmpdir:
            env = {**env_dict, "DATA_DIR": tmpdir}
            for k, v in env.items():
                monkeypatch.setenv(k, v)
            yield


@pytest.fixture()
def set_minimal_env(monkeypatch):
    yield from _env(monkeypatch, MINIMAL_ENV)


@pytest.fixture()
def set_full_env(monkeypatch):
    yield from _env(monkeypatch, FULL_ENV)


def test_generate_minimal_config(set_minimal_env):
    generate_vector_config_from_env("conf/vector.yaml.jinja", "conf/vector.yaml")
    res = validate_vector_config("conf/vector.yaml")
    assert res is True
    with open("conf/vector.yaml") as f:
        decoded = yaml.safe_load(f)
    assert decoded["sources"]["file"]["include"] == ["/foo/bar.log", "/bar/baz.log"]
    assert decoded["sinks"]["loki"]["endpoint"] == "http://localhost:3100/api/v1/push"
    assert decoded["sinks"]["loki"]["labels"] == {"job": "test", "instance": "test"}
    os.remove("conf/vector.yaml")


def test_generate_full_config(set_full_env):
    generate_vector_config_from_env("conf/vector.yaml.jinja", "conf/vector.yaml")
    res = validate_vector_config("conf/vector.yaml")
    assert res is True
    with open("conf/vector.yaml") as f:
        decoded = yaml.safe_load(f)
    assert decoded["sinks"]["loki"]["tenant_id"] == "123"
    assert decoded["sinks"]["loki"]["auth"]["strategy"] == "basic"
    assert decoded["sinks"]["loki"]["auth"]["user"] == "foo"
    assert decoded["sinks"]["loki"]["auth"]["password"] == "bar"
    os.remove("conf/vector.yaml")
