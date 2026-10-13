"""Unit tests for the application factory (Step 1, prompt 2)."""

from __future__ import annotations

import pytest
from flask import Flask

import wbms
from wbms import config, create_app
from wbms.config import ConfigError, load_settings


@pytest.fixture
def settings():
    return load_settings({"SECRET_KEY": "test-secret"})


@pytest.fixture
def client(settings):
    return create_app(settings).test_client()


def test_create_app_returns_a_flask_app(settings):
    assert isinstance(create_app(settings), Flask)


def test_health_returns_status_ok_as_json(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.is_json
    assert response.get_json() == {"status": "ok"}


def test_health_only_allows_get(client):
    assert client.post("/health").status_code == 405


def test_unknown_route_returns_404(client):
    assert client.get("/no-such-page").status_code == 404


def test_settings_are_stored_on_app_extensions(settings):
    app = create_app(settings)
    assert app.extensions["wbms_settings"] is settings


def test_secret_key_is_applied_to_flask_config(settings):
    assert create_app(settings).config["SECRET_KEY"] == "test-secret"


def test_each_call_returns_an_independent_app(settings):
    assert create_app(settings) is not create_app(settings)


def test_settings_are_loaded_from_environment_when_not_given(monkeypatch, tmp_path):
    monkeypatch.setattr(config, "ENV_FILE", tmp_path / "missing.env")
    monkeypatch.setenv("SECRET_KEY", "from-env")
    app = create_app()
    assert app.config["SECRET_KEY"] == "from-env"
    assert app.test_client().get("/health").status_code == 200


def test_create_app_fails_fast_when_config_is_invalid(monkeypatch, tmp_path):
    monkeypatch.setattr(config, "ENV_FILE", tmp_path / "missing.env")
    monkeypatch.setenv("SECRET_KEY", "temp")
    monkeypatch.delenv("SECRET_KEY")
    with pytest.raises(ConfigError, match="SECRET_KEY"):
        create_app()


def test_create_app_calls_register_blueprints(settings, monkeypatch):
    calls = []
    monkeypatch.setattr(wbms, "register_blueprints", calls.append)
    app = create_app(settings)
    assert calls == [app]
