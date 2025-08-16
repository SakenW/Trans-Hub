# packages/server/scripts/check_test_environment.py
"""
测试环境诊断脚本 (v3.0.0)

本脚本作为独立的健康探针，用于在运行 `pytest` 之前，快速验证测试环境
的数据库连通性。

核心价值:
- 最小化依赖: 不依赖 Typer 或复杂的应用状态，确保在应用本身或测试框架
  出现问题时，仍能独立进行环境诊断。
- 职责单一: 只做一件事——加载测试配置并尝试连接数据库。

用法:
    poetry run python packages/server/scripts/check_test_environment.py
"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

from sqlalchemy import text

# --- 路径设置，确保能导入 bootstrap ---
try:
    SRC_DIR = Path(__file__).resolve().parents[2] / "src"
    if str(SRC_DIR) not in sys.path:
        sys.path.insert(0, str(SRC_DIR))
    from trans_hub.bootstrap import create_app_config
    from trans_hub.infrastructure.db import create_async_db_engine, dispose_engine
except ImportError as e:
    sys.stderr.write(f"错误: 无法导入项目模块。请确保从项目根目录运行。\n{e}\n")
    sys.exit(1)


async def main() -> None:
    """加载测试配置，连接一次数据库，然后释放连接池。"""
    print("🩺 正在诊断测试环境数据库连接...")
    print("-" * 40)
    try:
        cfg = create_app_config(env_mode="test")
        db_url_masked = cfg.database.url.replace(
            cfg.database.url.split("@")[0].split("://")[-1], "user:***"
        )
        print(f"  - 目标数据库: {db_url_masked}")

        eng = create_async_db_engine(cfg)
        try:
            async with eng.connect() as conn:
                result = await conn.execute(text("SELECT 1"))
                assert result.scalar_one() == 1
            print("  - [✅] 连接成功。")
        finally:
            await dispose_engine(eng)
            print("  - [✅] 连接池已成功释放。")

        print("-" * 40)
        print("\n🎉 诊断通过：测试环境配置正确，数据库可达。")

    except Exception as e:
        print(f"\n❌ 诊断失败: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())