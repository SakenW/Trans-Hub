import json
from unittest.mock import AsyncMock, patch

from typer.testing import CliRunner

from trans_hub.cli import app


def test_logging_configuration_applied_json() -> None:
    runner = CliRunner()

    with (
        patch("trans_hub.cli.Coordinator") as MockCoordinator,
        patch("trans_hub.persistence.sqlite.SQLitePersistenceHandler"),
        patch("trans_hub.cli.gc_command") as mock_gc_command,
    ):
        MockCoordinator.return_value.initialize = AsyncMock()
        mock_gc_command.return_value = None
        result = runner.invoke(
            app, ["gc", "--dry-run"], env={"TH_LOGGING__FORMAT": "json"}
        )

    assert result.exit_code == 0
    found = False
    for line in result.output.splitlines():
        try:
            data = json.loads(line)
        except json.JSONDecodeError:
            continue
        if data.get("event") == "日志系统已配置完成。":
            assert data.get("log_format") == "json"
            assert data.get("app_log_level") == "INFO"
            found = True
            break
    assert found, "logging setup message not found"
