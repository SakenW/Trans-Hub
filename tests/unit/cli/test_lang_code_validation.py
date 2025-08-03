from unittest.mock import MagicMock, patch

from typer.testing import CliRunner

from trans_hub.cli import app

runner = CliRunner()


def test_worker_invalid_lang_code() -> None:
    """Worker command should fail on invalid language codes."""
    with patch("trans_hub.cli._initialize_coordinator") as mock_init:
        mock_init.return_value = (MagicMock(), MagicMock())
        result = runner.invoke(app, ["worker", "--lang", "invalid-lang"])
    assert result.exit_code != 0
    assert "格式无效" in result.output


def test_request_invalid_target_lang() -> None:
    """Request command should fail on invalid language codes."""
    with patch("trans_hub.cli._initialize_coordinator") as mock_init:
        mock_init.return_value = (MagicMock(), MagicMock())
        result = runner.invoke(app, ["request", "hello", "--target", "bad-code"])
    assert result.exit_code != 0
    assert "格式无效" in result.output
