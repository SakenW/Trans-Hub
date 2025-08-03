"""Very small stub of :mod:`cachetools` used in tests.

Only the ``LRUCache`` and ``TTLCache`` classes are provided and they behave
like plain dictionaries.  This is sufficient for the configuration module to
instantiate them during tests without the real dependency.
"""

from __future__ import annotations


class LRUCache(dict):  # pragma: no cover - behaviour is trivial
    def __init__(self, maxsize: int | None = None, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)


class TTLCache(dict):  # pragma: no cover - behaviour is trivial
    def __init__(self, maxsize: int | None = None, ttl: int | None = None, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)


__all__ = ["LRUCache", "TTLCache"]

