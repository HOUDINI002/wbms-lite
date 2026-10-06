"""Unit tests for wbms.config (Step 1, prompt 1)."""

from __future__ import annotations

import dataclasses
import os

import pytest

from wbms import config
from wbms.config import ConfigError, Settings, load_settings

DARAJA_ENV = {
    "SECRET_KEY": "test-secret",
    "PAYMENT_GATEWAY": "daraja",
    "CALLBACK_SECRET": "cb-secret",
    "DARAJA_CONSUMER_KEY": "ck",
    "DARAJA_CONSUMER_SECRET": "cs",
    "DARAJA_SHORTCODE": "174379",
    "DARAJA_PASSKEY": "pk",
    "DARAJA_BASE_URL": "https://sandbox.example.test",
}


# --- defaults -------------------------------------------------------------


def test_defaults_when_only_secret_key_is_given():
    s = load_settings({"SECRET_KEY": "abc"})
    assert s.SECRET_KEY == "abc"
    assert s.DATABASE_PATH == "instance/wbms.sqlite3"
    assert s.PAYMENT_GATEWAY == "mock"
    assert s.ROUTER_ADAPTER == "mock"
    assert s.CALLBACK_SECRET == ""
    assert s.DARAJA_BASE_URL == ""


def test_blank_values_fall_back_to_defaults():
    s = load_settings(
        {"SECRET_KEY": "abc", "DATABASE_PATH": "  ", "PAYMENT_GATEWAY": ""}
    )
    assert s.DATABASE_PATH == "instance/wbms.sqlite3"
    assert s.PAYMENT_GATEWAY == "mock"


# --- overrides ------------------------------------------------------------


def test_overrides_are_applied():
    s = load_settings(
        {
            "SECRET_KEY": "abc",
            "DATABASE_PATH": "data/other.db",
            "ROUTER_ADAPTER": "mikrotik",
        }
    )
    assert s.DATABASE_PATH == "data/other.db"
    assert s.ROUTER_ADAPTER == "mikrotik"


def test_adapter_names_are_trimmed_and_case_insensitive():
    s = load_settings(
        {"SECRET_KEY": "abc", "PAYMENT_GATEWAY": " MOCK ", "ROUTER_ADAPTER": "Mikrotik"}
    )
    assert s.PAYMENT_GATEWAY == "mock"
    assert s.ROUTER_ADAPTER == "mikrotik"


def test_complete_daraja_configuration_loads():
    s = load_settings(DARAJA_ENV)
    assert s.PAYMENT_GATEWAY == "daraja"
    assert s.DARAJA_SHORTCODE == "174379"
    assert s.DARAJA_BASE_URL == "https://sandbox.example.test"


def test_mock_gateway_does_not_require_daraja_values():
    # No DARAJA_* and no CALLBACK_SECRET: must still load.
    assert load_settings({"SECRET_KEY": "abc", "PAYMENT_GATEWAY": "mock"})


# --- missing / invalid values --------------------------------------------


def test_missing_secret_key_raises_config_error():
    with pytest.raises(ConfigError, match="SECRET_KEY"):
        load_settings({})


def test_blank_secret_key_counts_as_missing():
    with pytest.raises(ConfigError, match="SECRET_KEY"):
        load_settings({"SECRET_KEY": "   "})


@pytest.mark.parametrize("name", config.DARAJA_REQUIRED)
def test_each_missing_daraja_value_is_reported_by_name(name):
    env = {k: v for k, v in DARAJA_ENV.items() if k != name}
    with pytest.raises(ConfigError, match=name):
        load_settings(env)


def test_all_missing_daraja_values_are_listed_together():
    with pytest.raises(ConfigError) as excinfo:
        load_settings({"SECRET_KEY": "abc", "PAYMENT_GATEWAY": "daraja"})
    message = str(excinfo.value)
    for name in config.DARAJA_REQUIRED:
        assert name in message


@pytest.mark.parametrize(
    "name, value",
    [("PAYMENT_GATEWAY", "paypal"), ("ROUTER_ADAPTER", "cisco")],
)
def test_unknown_adapter_name_raises_config_error(name, value):
    with pytest.raises(ConfigError, match=name):
        load_settings({"SECRET_KEY": "abc", name: value})


def test_config_error_is_a_value_error():
    assert issubclass(ConfigError, ValueError)


def test_error_message_never_contains_secret_values():
    env = dict(DARAJA_ENV)
    del env["DARAJA_PASSKEY"]
    with pytest.raises(ConfigError) as excinfo:
        load_settings(env)
    message = str(excinfo.value)
    assert "DARAJA_PASSKEY" in message  # names are shown ...
    assert "test-secret" not in message  # ... values never are
    assert "cb-secret" not in message


# --- the Settings object --------------------------------------------------


def test_settings_are_frozen():
    s = load_settings({"SECRET_KEY": "abc"})
    with pytest.raises(dataclasses.FrozenInstanceError):
        s.SECRET_KEY = "changed"  # type: ignore[misc]


def test_repr_hides_secret_values():
    text = repr(load_settings(DARAJA_ENV))
    assert "test-secret" not in text
    assert "cb-secret" not in text
    assert "PAYMENT_GATEWAY='daraja'" in text  # non-secret fields still shown


def test_settings_constructor_requires_secret_key():
    with pytest.raises(TypeError):
        Settings()  # type: ignore[call-arg]


# --- reading the real environment and .env -------------------------------


def _forget(monkeypatch, *names):
    """Make sure each variable is absent now AND restored after the test."""
    for name in names:
        monkeypatch.setenv(name, "placeholder")  # records the original state
        monkeypatch.delenv(name)


def test_load_settings_without_argument_reads_os_environ(monkeypatch, tmp_path):
    monkeypatch.setattr(config, "ENV_FILE", tmp_path / "missing.env")
    monkeypatch.setenv("SECRET_KEY", "from-os")
    monkeypatch.setenv("DATABASE_PATH", "from-os.db")
    s = load_settings()
    assert s.SECRET_KEY == "from-os"
    assert s.DATABASE_PATH == "from-os.db"


def test_dotenv_file_is_loaded(monkeypatch, tmp_path):
    env_file = tmp_path / ".env"
    env_file.write_text(
        "SECRET_KEY=from-file\nROUTER_ADAPTER=mikrotik\n", encoding="utf-8"
    )
    monkeypatch.setattr(config, "ENV_FILE", env_file)
    _forget(monkeypatch, "SECRET_KEY", "ROUTER_ADAPTER")
    s = load_settings()
    assert s.SECRET_KEY == "from-file"
    assert s.ROUTER_ADAPTER == "mikrotik"


def test_real_environment_wins_over_dotenv(monkeypatch, tmp_path):
    env_file = tmp_path / ".env"
    env_file.write_text("SECRET_KEY=from-file\n", encoding="utf-8")
    monkeypatch.setattr(config, "ENV_FILE", env_file)
    monkeypatch.setenv("SECRET_KEY", "from-os")
    assert load_settings().SECRET_KEY == "from-os"


def test_explicit_mapping_ignores_os_environ_and_dotenv(monkeypatch, tmp_path):
    env_file = tmp_path / ".env"
    env_file.write_text("SECRET_KEY=from-file\n", encoding="utf-8")
    monkeypatch.setattr(config, "ENV_FILE", env_file)
    monkeypatch.setenv("SECRET_KEY", "from-os")
    assert load_settings({"SECRET_KEY": "from-mapping"}).SECRET_KEY == "from-mapping"
    assert os.environ["SECRET_KEY"] == "from-os"  # untouched
