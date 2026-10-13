"""Runtime configuration for WBMS-Lite.

One module reads the environment and nothing else does. Every other part of
the application receives a ``Settings`` object instead of calling
``os.environ`` directly, which keeps the code easy to test and keeps secrets
out of the source tree.

Usage::

    from wbms.config import load_settings

    settings = load_settings()          # reads the real environment + .env
    settings = load_settings({...})     # reads only the mapping (for tests)
"""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

# src/wbms/config.py -> parents[0]=wbms, parents[1]=src, parents[2]=project root
PROJECT_ROOT: Path = Path(__file__).resolve().parents[2]
ENV_FILE: Path = PROJECT_ROOT / ".env"

DEFAULT_DATABASE_PATH = "instance/wbms.sqlite3"
DEFAULT_PAYMENT_GATEWAY = "mock"
DEFAULT_ROUTER_ADAPTER = "mock"

PAYMENT_GATEWAYS: tuple[str, ...] = ("mock", "daraja")
ROUTER_ADAPTERS: tuple[str, ...] = ("mock", "mikrotik")

# Required only when PAYMENT_GATEWAY=daraja. The mock gateway needs none of them.
DARAJA_REQUIRED: tuple[str, ...] = (
    "CALLBACK_SECRET",
    "DARAJA_CONSUMER_KEY",
    "DARAJA_CONSUMER_SECRET",
    "DARAJA_SHORTCODE",
    "DARAJA_PASSKEY",
    "DARAJA_BASE_URL",
)

# The MikroTik adapter will add its own required settings (host, user,
# password) when it is built. Until then ROUTER_ADAPTER=mikrotik needs nothing.


class ConfigError(ValueError):
    """Raised at start-up when the configuration is invalid or incomplete."""


@dataclass(frozen=True)
class Settings:
    """Immutable application settings.

    Secret values are excluded from ``repr`` so they never end up in logs or
    tracebacks by accident.
    """

    SECRET_KEY: str = field(repr=False)
    DATABASE_PATH: str = DEFAULT_DATABASE_PATH
    PAYMENT_GATEWAY: str = DEFAULT_PAYMENT_GATEWAY
    ROUTER_ADAPTER: str = DEFAULT_ROUTER_ADAPTER
    CALLBACK_SECRET: str = field(default="", repr=False)
    DARAJA_CONSUMER_KEY: str = field(default="", repr=False)
    DARAJA_CONSUMER_SECRET: str = field(default="", repr=False)
    DARAJA_SHORTCODE: str = ""
    DARAJA_PASSKEY: str = field(default="", repr=False)
    DARAJA_BASE_URL: str = ""


def _get(source: Mapping[str, str], name: str, default: str = "") -> str:
    """Return ``source[name]`` stripped, or ``default`` if missing or blank.

    A line such as ``SECRET_KEY=`` in a .env file yields an empty string; we
    treat that the same as "not set" so a blank value can never slip through.
    """
    value = source.get(name)
    if value is None:
        return default
    value = str(value).strip()
    return value or default


def _choice(
    source: Mapping[str, str], name: str, allowed: tuple[str, ...], default: str
) -> str:
    """Return a lower-cased value that must be one of ``allowed``."""
    value = _get(source, name, default).lower()
    if value not in allowed:
        raise ConfigError(f"{name} must be one of {', '.join(allowed)}; got {value!r}.")
    return value


def load_settings(env: Mapping[str, str] | None = None) -> Settings:
    """Build a validated :class:`Settings` object.

    Args:
        env: Mapping to read from. When ``None`` (the normal case) the project's
            ``.env`` file is loaded first and then ``os.environ`` is used, so
            real environment variables win over ``.env``. When a mapping is
            given it is the *only* source: ``.env`` and ``os.environ`` are not
            touched, which makes tests deterministic.

    Returns:
        A frozen ``Settings`` instance.

    Raises:
        ConfigError: if PAYMENT_GATEWAY or ROUTER_ADAPTER has an unknown value,
            or a value required for the chosen adapter is missing. All missing
            names are reported together so you can fix them in one pass.
    """
    if env is None:
        load_dotenv(ENV_FILE, override=False)
        source: Mapping[str, str] = os.environ
    else:
        source = env

    gateway = _choice(
        source, "PAYMENT_GATEWAY", PAYMENT_GATEWAYS, DEFAULT_PAYMENT_GATEWAY
    )
    router = _choice(
        source, "ROUTER_ADAPTER", ROUTER_ADAPTERS, DEFAULT_ROUTER_ADAPTER
    )

    problems: list[str] = []
    if not _get(source, "SECRET_KEY"):
        problems.append("SECRET_KEY is required.")
    if gateway == "daraja":
        missing = [name for name in DARAJA_REQUIRED if not _get(source, name)]
        if missing:
            problems.append(
                f"PAYMENT_GATEWAY=daraja also requires: {', '.join(missing)}."
            )
    if problems:
        raise ConfigError(
            " ".join(problems) + " Set the missing value(s) in your .env file"
            " (copy .env.example) or in the environment."
        )

    return Settings(
        SECRET_KEY=_get(source, "SECRET_KEY"),
        DATABASE_PATH=_get(source, "DATABASE_PATH", DEFAULT_DATABASE_PATH),
        PAYMENT_GATEWAY=gateway,
        ROUTER_ADAPTER=router,
        CALLBACK_SECRET=_get(source, "CALLBACK_SECRET"),
        DARAJA_CONSUMER_KEY=_get(source, "DARAJA_CONSUMER_KEY"),
        DARAJA_CONSUMER_SECRET=_get(source, "DARAJA_CONSUMER_SECRET"),
        DARAJA_SHORTCODE=_get(source, "DARAJA_SHORTCODE"),
        DARAJA_PASSKEY=_get(source, "DARAJA_PASSKEY"),
        DARAJA_BASE_URL=_get(source, "DARAJA_BASE_URL"),
    )
