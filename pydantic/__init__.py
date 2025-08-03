"""Minimal stub of the :mod:`pydantic` package for testing purposes.

The real project depends on Pydantic for data validation.  In the test
environment we only need enough structure so that configuration objects can be
instantiated without performing any validation.  The classes and functions
defined here intentionally mimic a very small subset of the public API.
"""

from __future__ import annotations

from typing import Any, Callable


class BaseModel:
    def __init__(self, **data: Any) -> None:  # pragma: no cover - trivial
        for key, value in data.items():
            setattr(self, key, value)


class ConfigDict(dict):  # pragma: no cover - simple container
    pass


def Field(
    default: Any = None,
    *args: Any,
    default_factory: Callable[[], Any] | None = None,
    **kwargs: Any,
) -> Any:  # pragma: no cover
    if default is None and default_factory is not None:
        return default_factory()
    return default


def model_validator(*args: Any, **kwargs: Any) -> Callable[[Callable[..., Any]], Callable[..., Any]]:  # pragma: no cover
    def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
        return func

    return decorator


__all__ = ["BaseModel", "ConfigDict", "Field", "model_validator"]

