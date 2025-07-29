# tools/doc_translator/main_cli.py
"""Trans-Hub 文档翻译同步工具的命令行入口。"""

import sys
from pathlib import Path

# 将项目根目录添加到 Python 路径
PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

import asyncio  # noqa: E402
from typing import Annotated, List  # noqa: E402

import questionary  # noqa: E402
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

from tools.doc_translator.models import LangCode  # noqa: E402
from tools.doc_translator.parser import parse_document  # noqa: E402
from tools.doc_translator.publisher import DocPublisher  # noqa: E402
from tools.doc_translator.renderer import DocRenderer  # noqa: E402
from tools.doc_translator.scanner import DocScanner  # noqa: E402
from tools.doc_translator.synchronizer import DocSynchronizer  # noqa: E402

# --- 默认配置 ---
DOCS_DIR = PROJECT_ROOT / "docs"
DB_FILE_PATH = PROJECT_ROOT / "tools" / "doc_translator" / "docs_translations.db"
DEFAULT_SOURCE_LANG: LangCode = "zh"
DEFAULT_TARGET_LANGS: List[LangCode] = ["en"]
DEFAULT_MAIN_LANG: LangCode = "en"

# --- Typer CLI 应用 ---
app = typer.Typer(
    name="doc-translator",
    help="Trans-Hub 文档翻译同步工具: 翻译并发布多语言 Markdown 文档。",
    no_args_is_help=False,  # 设置为 False 以允许 invoke_without_command 生效
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
    coordinator = None
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
        if coordinator and getattr(coordinator, 'initialized', False):
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


def start_interactive_mode() -> None:
    """启动交互式菜单模式。"""
    log.info("进入交互式模式...")
    
    action = questionary.select(
        "请选择您要执行的操作:",
        choices=[
            "1. 同步 (翻译 + 发布)",
            "2. 仅翻译",
            "3. 仅发布双语根文件",
            "4. 退出",
        ],
        pointer="👉",
    ).ask()

    if action is None or action.endswith("退出"):
        log.info("操作已取消，退出程序。")
        raise typer.Exit()

    if action.startswith("1") or action.startswith("2"):  # 同步或仅翻译
        source_lang = questionary.text("请输入源语言:", default=DEFAULT_SOURCE_LANG).ask()
        target_langs_str = questionary.text(
            "请输入目标语言 (用逗号分隔):", default=",".join(DEFAULT_TARGET_LANGS)
        ).ask()
        if not source_lang or not target_langs_str:
            log.error("源语言和目标语言不能为空。")
            raise typer.Exit(code=1)
            
        target_langs = [lang.strip() for lang in target_langs_str.split(",")]
        default_lang = questionary.text("请输入项目的默认语言:", default=DEFAULT_MAIN_LANG).ask()
        if not default_lang:
            log.error("默认语言不能为空。")
            raise typer.Exit(code=1)

        asyncio.run(
            run_translation_pipeline(
                source_lang=source_lang,
                target_langs=target_langs,
                default_lang=default_lang,
                force_retranslate=False,
            )
        )
        
        if action.startswith("1"):
            log.info("翻译流程完成，现在开始执行发布...")
            run_publish_pipeline(default_lang)
            log.info("🎉 全部同步操作完成！")

    elif action.startswith("3"):  # 仅发布
        default_lang = questionary.text("请输入项目的默认语言:", default=DEFAULT_MAIN_LANG).ask()
        if not default_lang:
            log.error("默认语言不能为空。")
            raise typer.Exit(code=1)
        run_publish_pipeline(default_lang)


# --- Typer 子命令定义 ---
@app.command("translate")
def translate_command(
    source_lang: Annotated[str, typer.Option("--source", "-s", help="源语言代码。")] = DEFAULT_SOURCE_LANG,
    target_lang: Annotated[list[str], typer.Option("--target", "-t", help="一个或多个目标语言代码。")] = DEFAULT_TARGET_LANGS,
    default_lang: Annotated[str, typer.Option("--default", "-d", help="项目使用的默认语言。")] = DEFAULT_MAIN_LANG,
    force_retranslate: Annotated[bool, typer.Option("--force", "-f", help="强制重新翻译所有内容。")] = False,
) -> None:
    """【翻译】扫描、翻译并将所有文档渲染到 docs/<lang> 目录。"""
    setup_logging(log_level="INFO")
    load_dotenv()
    asyncio.run(
        run_translation_pipeline(
            source_lang=source_lang,
            target_langs=target_langs,
            default_lang=default_lang,
            force_retranslate=force_retranslate,
        )
    )

@app.command("publish")
def publish_command(
    default_lang: Annotated[str, typer.Option("--default", "-d", help="项目默认语言，用于定位发布源。")] = DEFAULT_MAIN_LANG,
) -> None:
    """【发布】将根文件以可切换的双语版本发布到项目根目录。"""
    setup_logging(log_level="INFO")
    run_publish_pipeline(default_lang)

@app.command("sync")
def sync_command(
    source_lang: Annotated[str, typer.Option("--source", "-s", help="源语言代码。")] = DEFAULT_SOURCE_LANG,
    target_lang: Annotated[list[str], typer.Option("--target", "-t", help="一个或多个目标语言代码。")] = DEFAULT_TARGET_LANGS,
    default_lang: Annotated[str, typer.Option("--default", "-d", help="项目默认语言。")] = DEFAULT_MAIN_LANG,
    force_retranslate: Annotated[bool, typer.Option("--force", "-f", help="强制重新翻译所有内容。")] = False,
) -> None:
    """【同步】执行完整的“翻译+发布”流程，一步到位。"""
    setup_logging(log_level="INFO")
    load_dotenv()
    asyncio.run(
        run_translation_pipeline(
            source_lang=source_lang,
            target_langs=target_langs,
            default_lang=default_lang,
            force_retranslate=force_retranslate,
        )
    )
    log.info("翻译流程完成，现在开始执行发布...")
    run_publish_pipeline(default_lang)
    log.info("🎉 全部同步操作完成！")


@app.callback(invoke_without_command=True)
def main_entrypoint(ctx: typer.Context) -> None:
    """
    Trans-Hub 文档翻译同步工具。
    直接运行将进入交互模式，也可使用 'translate', 'publish', 'sync' 子命令。
    """
    if ctx.invoked_subcommand is not None:
        return
    
    setup_logging(log_level="INFO")
    load_dotenv()
    try:
        start_interactive_mode()
    except (KeyboardInterrupt, typer.Exit):
        log.warning("用户已中断或退出操作。")
    except Exception:
        log.error("交互模式下发生未知错误。", exc_info=True)


if __name__ == "__main__":
    app()