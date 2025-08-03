"""Stub for :mod:`rich.console` providing a minimal :class:`Console` class."""

class Console:  # pragma: no cover - trivial behaviour
    def print(self, *args, **kwargs) -> None:
        text = " ".join(str(a) for a in args)
        if text:
            print(text)


__all__ = ["Console"]

