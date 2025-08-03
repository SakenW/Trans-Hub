import pytest
from typer.testing import CliRunner
from unittest.mock import MagicMock, patch

from trans_hub.cli import app


@pytest.fixture
def runner() -> CliRunner:
    return CliRunner()


def test_worker_requires_lang(runner: CliRunner) -> None:
    with patch("trans_hub.cli._initialize_coordinator") as mock_init, patch(
        "trans_hub.cli.run_worker"
    ) as mock_run_worker:
        mock_init.return_value = (MagicMock(), MagicMock())
        result = runner.invoke(app, ["worker"])
    assert result.exit_code != 0
    assert "--lang" in result.output
    mock_run_worker.assert_not_called()

