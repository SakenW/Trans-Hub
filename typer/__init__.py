"""A minimal stub implementation of the ``typer`` package used in tests.

This stub provides just enough functionality for the unit tests to import the
Trans‑Hub CLI modules without requiring the real third‑party dependency.  The
implementation intentionally keeps the behaviour extremely small – only the
attributes actually exercised by the tests are implemented.

The goal is not to be feature complete but to emulate the pieces of Typer that
are touched by the project:

* :class:`Typer` – used as a container for CLI commands.  Commands registered
  through ``@app.command`` are stored in ``registered_commands`` so tests can
  introspect them.
* :func:`Option` and :func:`Argument` – act as lightweight placeholders that
  simply return the provided default value.  They merely satisfy the type
  annotations present in the CLI code.
* :class:`Context` – a tiny object exposing ``invoked_subcommand`` and
  ``get_help`` so that ``main`` can interact with it during tests.
* :class:`Exit` – a subclass of :class:`SystemExit` mimicking Typer's ``Exit``
  exception.

Only what is required by the tests and the CLI modules is implemented here.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Dict, Optional


class Exit(SystemExit):
    """Replacement for :class:`typer.Exit`."""


def Option(default: Any, *args: Any, **kwargs: Any) -> Any:  # pragma: no cover -
    """Return the default value.

    The real Typer returns a special object understood by Click.  For the unit
    tests we simply return the default value which allows the function
    signatures to remain the same without pulling in the dependency.
    """

    return default


def Argument(default: Any, *args: Any, **kwargs: Any) -> Any:  # pragma: no cover
    """Return the default value, mirroring :func:`Option`."""

    return default


@dataclass
class Context:
    """Very small stand‑in for :class:`typer.Context` used in tests."""

    invoked_subcommand: Optional[str] = None

    def get_help(self) -> str:  # pragma: no cover - trivial
        """Return a dummy help message."""

        return "help"


class Typer:
    """A minimal container mimicking :class:`typer.Typer`."""

    def __init__(self, help: str | None = None) -> None:
        self.help = help
        self.registered_commands: Dict[str, Callable[..., Any]] = {}
        self._callback: Optional[Callable[..., Any]] = None

    # ------------------------------------------------------------------
    # Registration helpers
    def command(self, name: str | None = None, *args: Any, **kwargs: Any) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
        """Register a command function."""

        def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
            cmd_name = name or func.__name__
            self.registered_commands[cmd_name] = func
            return func

        return decorator

    def add_typer(self, app: "Typer", name: str, *args: Any, **kwargs: Any) -> None:
        """Register a sub application."""

        self.registered_commands[name] = app  # type: ignore[assignment]

    def callback(self, *args: Any, **kwargs: Any) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
        """Register the main callback."""

        def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
            self._callback = func
            return func

        return decorator

    # ------------------------------------------------------------------
    # Invocation support (extremely small and only for tests)
    def __call__(self, *args: Any, **kwargs: Any) -> Any:  # pragma: no cover -
        if self._callback is None:
            raise RuntimeError("No callback registered")
        ctx = Context()
        return self._callback(ctx, *args, **kwargs)


__all__ = [
    "Typer",
    "Option",
    "Argument",
    "Context",
    "Exit",
]

