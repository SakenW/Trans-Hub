"""Stub module for :mod:`pydantic_settings`.

The CLI configuration uses :class:`BaseSettings` and ``SettingsConfigDict``.
Here they are implemented as very small shells around the stubbed
``pydantic.BaseModel`` class so that tests can run without the external
dependency.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel


class BaseSettings(BaseModel):  # pragma: no cover - trivial container
    model_config: dict[str, Any] = {}


class SettingsConfigDict(dict):  # pragma: no cover - simple alias
    pass


__all__ = ["BaseSettings", "SettingsConfigDict"]

