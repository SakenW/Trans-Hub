# src/trans_hub/adapters/cli/commands/request.py
"""
CLI 命令: `request`

该命令族负责处理所有与翻译请求相关的操作，例如创建新的翻译请求。
"""

import asyncio
import json
from typing import Annotated

import typer
from dependency_injector.wiring import Provide, inject
from rich import print_json

from trans_hub.application.coordinator import Coordinator
from trans_hub.di.container import AppContainer

# --- CLI 命令定义 ---

app = typer.Typer(name="request", help="创建和管理翻译请求。")


@inject
async def _request_new_logic(
    project_id: str,
    source_locale: str,
    target_locales: list[str],
    keys: dict[str, str],
    coordinator: Coordinator = Provide[AppContainer.coordinator],
) -> None:
    """异步的业务逻辑实现。"""
    # 1. 调用应用服务
    request_id = await coordinator.create_request(
        project_id=project_id,
        source_locale=source_locale,
        target_locales=target_locales,
        keys=keys,
    )

    # 2. 打印结果
    result = {
        "status": "success",
        "message": "翻译请求已成功创建。",
        "request_id": str(request_id),
    }
    print_json(data=result)


@app.command(
    name="new",
    help="创建一个新的翻译请求。",
    no_args_is_help=True,
)
def request_new_cli(
    project_id: Annotated[
        str,
        typer.Option(
            "--project",
            "-p",
            help="项目 ID。",
            show_default=False,
        ),
    ],
    source_locale: Annotated[
        str,
        typer.Option(
            "--source",
            "-s",
            help="源语言代码 (BCP 47)。",
            show_default=False,
        ),
    ],
    target_locales: Annotated[
        str,
        typer.Option(
            "--targets",
            "-t",
            help="目标语言代码列表，以逗号分隔。",
            show_default=False,
        ),
    ],
    keys: Annotated[
        str,
        typer.Option(
            "--keys",
            "-k",
            help="要翻译的键值对 (JSON 格式字符串)。",
            show_default=False,
        ),
    ],
) -> None:
    """同步的 CLI 接口函数，内部调用异步业务逻辑。"""
    # 1. 解析输入
    try:
        keys_data = json.loads(keys)
    except json.JSONDecodeError:
        raise typer.BadParameter(f"'{keys}' 不是一个有效的 JSON。", param_hint="--keys")

    target_locales_list = [locale.strip() for locale in target_locales.split(",")]

    # 2. 调用异步业务逻辑
    asyncio.run(
        _request_new_logic(
            project_id=project_id,
            source_locale=source_locale,
            target_locales=target_locales_list,
            keys=keys_data,
        )
    )
