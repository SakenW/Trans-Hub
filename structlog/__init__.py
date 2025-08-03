"""Minimal stub of :mod:`structlog` for unit testing.

The production project uses ``structlog`` for structured logging.  In the test
environment we only need an object returned by :func:`get_logger` that exposes
``info``, ``debug``, ``warning`` and ``error`` methods which simply ignore their
arguments.
"""

from __future__ import annotations

from typing import Any


class _Logger:  # pragma: no cover - trivial behaviour
    def info(self, *args: Any, **kwargs: Any) -> None: pass
    def debug(self, *args: Any, **kwargs: Any) -> None: pass
    def warning(self, *args: Any, **kwargs: Any) -> None: pass
    def error(self, *args: Any, **kwargs: Any) -> None: pass


def get_logger(*args: Any, **kwargs: Any) -> _Logger:  # pragma: no cover
    return _Logger()


__all__ = ["get_logger"]

