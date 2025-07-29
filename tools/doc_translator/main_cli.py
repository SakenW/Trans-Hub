# tools/doc_translator/main_cli.py
"""Trans-Hub 文档翻译同步工具的命令行入口。"""

import sys
from pathlib import Path

# 将项目根目录添加到 Python 路径，以便能找到 trans_hub 和 tools 模块
PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

# 所有在此之后的 import 都会引发 E402，我们使用 noqa 来抑制这个警告
import asyncio  # noqa: E402
from typing import Annotated  # noqa: E402

import structlog  # noqa: E402
import typer  # noqa: E402
from dotenv import load_dotenv  # noqa: E402

# 2. 本地工具模块导入
from tools.doc_translator.models import LangCode  # noqa: E402
from tools.doc_translator.parser import parse_document  # noqa: E402
from tools.doc_translator.publisher import DocPublisher  # noqa: E402
from tools.doc_translator.renderer import DocRenderer  # noqa: E402
from tools.doc_translator.scanner import DocScanner  # noqa: E402
from tools.doc_translator.synchronizer import DocSynchronizer  # noqa: E402

# --- 核心修正：重新组织导入块并正确使用 noqa ---
# 1. trans_hub 核心组件导入
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

# --- 默认配置 ---
DOCS_DIR = PROJECT_ROOT / "docs"
DB_FILE_PATH = PROJECT_ROOT / "tools" / "doc_translator" / "docs_translations.db"
DEFAULT_SOURCE_LANG: LangCode = "zh"
DEFAULT_TARGET_LANGS: list[LangCode] = ["en"]
DEFAULT_MAIN_LANG: LangCode = "en"

# --- Typer CLI 应用 ---
app = typer.Typer(
    name="doc-translator",
    help="Trans-Hub 文档翻译同步工具: 翻译并发布多语言 Markdown 文档。",
    no_args_is_help=True,
    add_completion=False,
)
log = structlog.get_logger(__name__)


# --- 核心逻辑函数 ---


async def run_translation_pipeline(
    source_lang: LangCode,
    target_langs: list[LangCode],
    default_lang: LangCode,
    force_retranslate: bool,
) -> None:
    """执行翻译的核心逻辑，不包含发布。"""
    log.info("▶️ 启动文档翻译流水线...")
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
    coordinator = None  # 在 try 外部声明
    try:
        coordinator = Coordinator(config, handler)
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

        dispatch_tasks = [
            synchronizer.dispatch_document_to_trans_hub(doc) for doc in scanned_docs
        ]
        await asyncio.gather(*dispatch_tasks)

        await synchronizer.process_all_pending(target_langs)

        fetch_tasks = [
            synchronizer.fetch_translations_for_document(doc) for doc in scanned_docs
        ]
        await asyncio.gather(*fetch_tasks)

        for doc in scanned_docs:
            renderer.render_document_to_file(doc)
        log.info("✅ 文档翻译完成！")
    finally:
        if coordinator and getattr(coordinator, "initialized", False):
            await coordinator.close()


def run_publish_pipeline(default_lang: LangCode) -> None:
    """执行发布的核心逻辑。"""
    log.info("▶️ 启动文档发布流程...")
    publisher = DocPublisher(
        docs_dir=DOCS_DIR,
        project_root=PROJECT_ROOT,
        default_lang=default_lang,
    )
    publisher.publish_root_files()
    log.info("✅ 双语根文件发布完成！")


# --- Typer 子命令定义 ---


@app.command("translate")
def translate_command(
    source_lang: Annotated[
        str, typer.Option("--source", "-s", help="源语言代码。")
    ] = DEFAULT_SOURCE_LANG,
    target_lang: Annotated[
        list[str], typer.Option("--target", "-t", help="一个或多个目标语言代码。")
    ] = DEFAULT_TARGET_LANGS,
    default_lang: Annotated[
        str, typer.Option("--default", "-d", help="项目使用的默认语言。")
    ] = DEFAULT_MAIN_LANG,
    force_retranslate: Annotated[
        bool, typer.Option("--force", "-f", help="强制重新翻译所有内容。")
    ] = False,
) -> None:
    """【翻译】扫描、翻译并将所有文档渲染到 docs/<lang> 目录。"""
    setup_logging(log_level="INFO")
    load_dotenv()
    asyncio.run(
        run_translation_pipeline(
            source_lang=source_lang,
            target_langs=target_lang,
            default_lang=default_lang,
            force_retranslate=force_retranslate,
        )
    )


@app.command("publish")
def publish_command(
    default_lang: Annotated[
        str, typer.Option("--default", "-d", help="项目默认语言，用于定位发布源。")
    ] = DEFAULT_MAIN_LANG,
) -> None:
    """【发布】将根文件以可切换的双语版本发布到项目根目录。"""
    setup_logging(log_level="INFO")
    run_publish_pipeline(default_lang)


@app.command("sync")
def sync_command(
    source_lang: Annotated[
        str, typer.Option("--source", "-s", help="源语言代码。")
    ] = DEFAULT_SOURCE_LANG,
    target_lang: Annotated[
        list[str], typer.Option("--target", "-t", help="一个或多个目标语言代码。")
    ] = DEFAULT_TARGET_LANGS,
    default_lang: Annotated[
        str, typer.Option("--default", "-d", help="项目默认语言。")
    ] = DEFAULT_MAIN_LANG,
    force_retranslate: Annotated[
        bool, typer.Option("--force", "-f", help="强制重新翻译所有内容。")
    ] = False,
) -> None:
    """【同步】执行完整的“翻译+发布”流程，一步到位。"""
    setup_logging(log_level="INFO")
    load_dotenv()

    asyncio.run(
        run_translation_pipeline(
            source_lang=source_lang,
            target_langs=target_lang,
            default_lang=default_lang,
            force_retranslate=force_retranslate,
        )
    )

    log.info("翻译流程完成，现在开始执行发布...")
    run_publish_pipeline(default_lang)

    log.info("🎉 全部同步操作完成！")


if __name__ == "__main__":
    app()
