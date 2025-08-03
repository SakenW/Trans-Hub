"""A tiny stub of the :mod:`questionary` package used in the CLI tests.

The real library provides rich interactive prompts.  For the purposes of unit
tests we only need a ``confirm`` function returning an object with an
``ask_async`` coroutine method.  The coroutine simply returns the predefined
result, allowing tests to control the behaviour by patching ``confirm``.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any


@dataclass
class _ConfirmPrompt:
    """Simple object mimicking the return value of ``questionary.confirm``."""

    result: bool

    async def ask_async(self) -> bool:  # pragma: no cover - trivial
        await asyncio.sleep(0)
        return self.result


def confirm(message: str, default: bool = False, auto_enter: bool | None = None) -> _ConfirmPrompt:
    """Return a :class:`_ConfirmPrompt` with the provided default result."""

    return _ConfirmPrompt(default)


__all__ = ["confirm"]

