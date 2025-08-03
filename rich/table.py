"""Stub for :mod:`rich.table` used in tests."""


class Table:  # pragma: no cover - trivial container
    def __init__(self, title: str | None = None) -> None:
        self.title = title

    def add_column(self, *args, **kwargs) -> None:
        pass

    def add_row(self, *args, **kwargs) -> None:
        pass


__all__ = ["Table"]

