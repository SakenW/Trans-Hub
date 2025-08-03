import pytest
from typer.testing import CliRunner

import trans_hub.cli as cli


class DummyCoordinator:
    def __init__(self, config, handler):
        self.initialized = False
        created.append(self)

    async def initialize(self):
        self.initialized = True

    async def request(self, *args, **kwargs):
        return None

    async def close(self):
        self.initialized = False


class DummyPersistenceHandler:
    def __init__(self, url):
        pass


class DummyConfig:
    database_url = "sqlite://"

    def __init__(self):
        pass


created = []


@pytest.fixture
def runner():
    return CliRunner()


def test_consecutive_commands_reinitialize_coordinator(monkeypatch, runner):
    monkeypatch.setattr(cli, "Coordinator", DummyCoordinator)
    monkeypatch.setattr(cli, "TransHubConfig", DummyConfig)
    monkeypatch.setattr(
        "trans_hub.persistence.sqlite.SQLitePersistenceHandler",
        DummyPersistenceHandler,
    )

    result1 = runner.invoke(cli.app, ["request", "hello", "--target", "zh"])
    assert result1.exit_code == 0
    assert cli._coordinator is None
    assert cli._loop is None

    result2 = runner.invoke(cli.app, ["request", "hello", "--target", "zh"])
    assert result2.exit_code == 0
    assert cli._coordinator is None
    assert cli._loop is None

    assert len(created) == 2
    assert created[0] is not created[1]
