# packages/server/tests/diagnose_pytest_env.py
"""
最小化诊断脚本（遵守技术宪章）

目标：在 pytest 之外快速自检 DSN 与连通性，并验证释放语义。
用法：
    poetry run python packages/server/tests/diagnose_pytest_env.py
"""

from __future__ import annotations

import asyncio

from sqlalchemy import text

from trans_hub.config_loader import load_config_from_env
from trans_hub.infrastructure.db import create_async_db_engine, dispose_engine


async def main() -> None:
    """加载配置，连一次库，释放连接池。"""
    cfg = load_config_from_env(mode="test", strict=True)
    eng = create_async_db_engine(cfg)
    async with eng.connect() as conn:
        await conn.execute(text("SELECT 1"))
    await dispose_engine(eng)
    print("✔ 诊断通过：连接与释放语义正确")


if __name__ == "__main__":
    asyncio.run(main())
