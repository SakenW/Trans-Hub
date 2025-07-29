# tools/doc_translator/main_cli.py
"""Trans-Hub 文档翻译同步工具的命令行入口。"""

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

import asyncio  # noqa: E402
from typing import Annotated  # noqa: E402

import structlog  # noqa: E402
import typer  # noqa: E402
from dotenv import load_dotenv  # noqa: E402

from trans_hub import (  # noqa: E402
    Coordinator,
    DefaultPersistenceHandler,
    EngineName,
    TransHubConfig,
)
from trans_hub.config import EngineConfigs  # noqa: E402
from trans_hub.db.schema_manager import apply_migrations  # noqa: E402
from trans_hub.engines.debug import DebugEngineConfig  # noqa: E402
from trans_hub.engines.openai import OpenAIEngineConfig  # noqa: E402
from trans_hub.engines.translators_engine import TranslatorsEngineConfig  # noqa: E402
from trans_hub.logging_config import setup_logging  # noqa: E402

from .models import LangCode  # noqa: E402
from .parser import parse_document  # noqa: E402
from .renderer import DocRenderer  # noqa: E402
from .scanner import DocScanner  # noqa: E402
from .synchronizer import DocSynchronizer  # noqa: E402

# --- 默认配置 ---
DOCS_DIR = PROJECT_ROOT / "docs"
DB_FILE_PATH = PROJECT_ROOT / "tools" / "doc_translator" / "docs_translations.db"
DEFAULT_SOURCE_LANG: LangCode = "zh"
DEFAULT_TARGET_LANGS: list[LangCode] = ["en"]
DEFAULT_MAIN_LANG: LangCode = "en"

# --- Typer CLI 应用 ---
app = typer.Typer(
    name="doc-translator",
    help="Trans-Hub 文档翻译同步工具: 扫描、翻译并生成多语言 Markdown 文档。",
)
log = structlog.get_logger(__name__)


async def run_sync_pipeline(
    source_lang: LangCode,
    target_langs: list[LangCode],
    default_lang: LangCode,
    force_retranslate: bool,
) -> None:
    """执行完整的端到端同步流水线。"""
    log.info("▶️ 启动文档翻译同步流水线...")
    if not DB_FILE_PATH.exists():
        log.info("数据库不存在，正在创建并迁移...", path=str(DB_FILE_PATH))
        apply_migrations(str(DB_FILE_PATH))

    openai_config = OpenAIEngineConfig()
    debug_config = DebugEngineConfig()
    translators_config = TranslatorsEngineConfig()
    engine_configs_instance = EngineConfigs(
        openai=openai_config, debug=debug_config, translators=translators_config
    )
    config = TransHubConfig(
        database_url=f"sqlite:///{DB_FILE_PATH.resolve()}",
        active_engine=EngineName.OPENAI,
        source_lang=source_lang,
        engine_configs=engine_configs_instance,
    )
    handler = DefaultPersistenceHandler(config.db_path)
    coordinator = Coordinator(config, handler)
    try:
        await coordinator.initialize()
        scanner = DocScanner(DOCS_DIR, source_lang, target_langs)
        synchronizer = DocSynchronizer(coordinator)
        renderer = DocRenderer(default_lang=default_lang, project_root=PROJECT_ROOT)
        scanned_docs = list(scanner.scan())
        if not scanned_docs:
            log.warning("未扫描到任何源文档，操作结束。")
            return
        for doc in scanned_docs:
            parse_document(doc)
        log.info("开始将所有文档的翻译任务分发给 Trans-Hub...")
        dispatch_tasks = [
            synchronizer.dispatch_document_to_trans_hub(doc) for doc in scanned_docs
        ]
        await asyncio.gather(*dispatch_tasks)
        log.info("所有任务已提交，开始驱动后台翻译处理...")
        await synchronizer.process_all_pending(target_langs)
        log.info("翻译处理完成，开始获取最新结果并渲染文件...")
        fetch_tasks = [
            synchronizer.fetch_translations_for_document(doc) for doc in scanned_docs
        ]
        await asyncio.gather(*fetch_tasks)
        for doc in scanned_docs:
            renderer.render_document_to_file(doc)
        log.info("✅ 文档翻译同步完成！")
    except Exception:
        log.error("文档同步过程中发生意外错误。", exc_info=True)
    finally:
        if coordinator and coordinator.initialized:
            await coordinator.close()


@app.callback(invoke_without_command=True)
def main_entrypoint(
    ctx: typer.Context,
    source_lang: Annotated[
        str, typer.Option("--source", "-s", help="源语言代码。")
    ] = DEFAULT_SOURCE_LANG,
    target_lang: Annotated[
        list[str], typer.Option("--target", "-t", help="一个或多个目标语言代码。")
    ] = DEFAULT_TARGET_LANGS,
    default_lang: Annotated[
        str, typer.Option("--default", "-d", help="项目根目录文件使用的默认语言。")
    ] = DEFAULT_MAIN_LANG,
    force_retranslate: Annotated[
        bool, typer.Option("--force", "-f", help="强制重新翻译所有内容，忽略现有缓存。")
    ] = False,
) -> None:
    """Trans-Hub 文档翻译同步工具。"""
    if ctx.invoked_subcommand is not None:
        return
    setup_logging(log_level="INFO")
    load_dotenv()
    asyncio.run(
        run_sync_pipeline(
            source_lang=source_lang,
            target_langs=target_lang,
            default_lang=default_lang,
            force_retranslate=force_retranslate,
        )
    )


if __name__ == "__main__":
    app()
