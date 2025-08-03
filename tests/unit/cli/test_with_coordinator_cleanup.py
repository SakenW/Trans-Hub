import importlib
import sys
import types
import unittest
from unittest.mock import AsyncMock, MagicMock


def _load_cli_with_stubs() -> types.ModuleType:
    """Import trans_hub.cli with minimal stubs for external deps."""
    # ---- stub typer ----
    class Exit(Exception):
        def __init__(self, code: int = 0) -> None:
            self.code = code
            super().__init__(code)

    class Typer:
        def __init__(self, *args, **kwargs) -> None:  # pragma: no cover - stub
            pass

        def add_typer(self, *args, **kwargs) -> None:  # pragma: no cover - stub
            return None

        def command(self, *args, **kwargs):  # pragma: no cover - stub
            def decorator(func):
                return func

            return decorator

        def callback(self, *args, **kwargs):  # pragma: no cover - stub
            def decorator(func):
                return func

            return decorator

    def Option(default=None, *args, **kwargs):  # pragma: no cover - stub
        return default

    def Argument(default=None, *args, **kwargs):  # pragma: no cover - stub
        return default

    class Context:  # pragma: no cover - stub
        pass

    typer_stub = types.ModuleType("typer")
    typer_stub.Typer = Typer
    typer_stub.Option = Option
    typer_stub.Argument = Argument
    typer_stub.Exit = Exit
    typer_stub.Context = Context
    sys.modules["typer"] = typer_stub

    # ---- stub rich ----
    class Console:
        def print(self, *args, **kwargs) -> None:  # pragma: no cover - stub
            return None

    console_mod = types.ModuleType("rich.console")
    console_mod.Console = Console
    table_mod = types.ModuleType("rich.table")

    class Table:
        def __init__(self, *args, **kwargs) -> None:  # pragma: no cover - stub
            pass

        def add_column(self, *args, **kwargs) -> None:  # pragma: no cover - stub
            pass

        def add_row(self, *args, **kwargs) -> None:  # pragma: no cover - stub
            pass

    table_mod.Table = Table
    sys.modules["rich"] = types.ModuleType("rich")
    sys.modules["rich.console"] = console_mod
    sys.modules["rich.table"] = table_mod

    # ---- stub structlog ----
    def get_logger(name=None):  # pragma: no cover - stub
        class Logger:
            def error(self, *a, **kw) -> None:
                pass

            def info(self, *a, **kw) -> None:
                pass

            def warning(self, *a, **kw) -> None:
                pass

        return Logger()

    structlog_mod = types.ModuleType("structlog")
    structlog_mod.get_logger = get_logger
    sys.modules["structlog"] = structlog_mod

    # ---- stub questionary ----
    questionary_mod = types.ModuleType("questionary")

    def confirm(*a, **kw):  # pragma: no cover - stub
        class Q:
            async def ask_async(self) -> bool:
                return True

            def ask(self) -> bool:
                return True

        return Q()

    questionary_mod.confirm = confirm
    sys.modules["questionary"] = questionary_mod

    # ---- stub trans_hub submodules ----
    config_mod = types.ModuleType("trans_hub.config")

    class TransHubConfig:  # pragma: no cover - stub
        pass

    class EngineName(str):  # pragma: no cover - stub
        pass

    config_mod.TransHubConfig = TransHubConfig
    config_mod.EngineName = EngineName
    sys.modules["trans_hub.config"] = config_mod

    coord_mod = types.ModuleType("trans_hub.coordinator")

    class Coordinator:  # pragma: no cover - stub
        async def initialize(self):
            pass

        async def close(self):
            pass

    coord_mod.Coordinator = Coordinator
    sys.modules["trans_hub.coordinator"] = coord_mod

    engines_mod = types.ModuleType("trans_hub.engines.base")

    class BaseContextModel:  # pragma: no cover - stub
        pass

    engines_mod.BaseContextModel = BaseContextModel
    sys.modules["trans_hub.engines.base"] = engines_mod

    persistence_mod = types.ModuleType("trans_hub.persistence")

    class DefaultPersistenceHandler:  # pragma: no cover - stub
        pass

    def create_persistence_handler(*a, **kw):  # pragma: no cover - stub
        pass

    persistence_mod.DefaultPersistenceHandler = DefaultPersistenceHandler
    persistence_mod.create_persistence_handler = create_persistence_handler
    sys.modules["trans_hub.persistence"] = persistence_mod

    types_mod = types.ModuleType("trans_hub.types")

    class TranslationStatus:  # pragma: no cover - stub
        pass

    types_mod.TranslationStatus = TranslationStatus
    sys.modules["trans_hub.types"] = types_mod

    sqlite_mod = types.ModuleType("trans_hub.persistence.sqlite")

    class SQLitePersistenceHandler:  # pragma: no cover - stub
        def __init__(self, *a, **kw) -> None:
            pass

        async def connect(self) -> None:
            pass

        async def reset_stale_tasks(self) -> None:
            pass

        async def close(self) -> None:
            pass

    sqlite_mod.SQLitePersistenceHandler = SQLitePersistenceHandler
    sys.modules["trans_hub.persistence.sqlite"] = sqlite_mod

    return importlib.import_module("trans_hub.cli")


class WithCoordinatorCleanupTest(unittest.TestCase):
    def test_resources_released_on_failure(self) -> None:
        cli_module = _load_cli_with_stubs()
        import typer  # type: ignore

        coordinator = MagicMock()
        coordinator.close = MagicMock()
        loop = MagicMock()
        loop.run_until_complete = MagicMock()
        loop.close = MagicMock()

        def mock_init(skip_init: bool = False):
            cli_module._coordinator = coordinator
            cli_module._loop = loop
            return coordinator, loop

        setattr(cli_module, "_initialize_coordinator", mock_init)

        @cli_module._with_coordinator
        def failing_command(coordinator, loop):  # type: ignore[no-untyped-def]
            raise RuntimeError("boom")

        with self.assertRaises(typer.Exit):
            failing_command()

        self.assertEqual(coordinator.close.call_count, 1)
        self.assertEqual(loop.run_until_complete.call_count, 1)
        self.assertEqual(loop.close.call_count, 1)
        self.assertIsNone(cli_module._coordinator)
        self.assertIsNone(cli_module._loop)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
