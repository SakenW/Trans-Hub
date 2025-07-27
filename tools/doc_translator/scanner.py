# tools/doc_translator/scanner.py
"""负责扫描文档目录，根据约定发现源文件，并为它们创建 Document 对象。"""

from collections.abc import Iterator
from pathlib import Path

import structlog

from .models import Document, LangCode

log = structlog.get_logger(__name__)


class DocScanner:
    """文档扫描器，扫描指定源语言目录。"""

    def __init__(
        self,
        docs_dir: Path,
        source_lang: LangCode,
        target_langs: list[LangCode],
    ):
        self.source_root_dir = docs_dir / source_lang
        self.source_lang = source_lang
        self.target_langs = target_langs

    def scan(self) -> Iterator[Document]:
        """执行扫描，并以迭代器方式返回发现的 Document 对象。"""
        log.info(
            "开始扫描源文档...",
            source_directory=str(self.source_root_dir),
        )

        if not self.source_root_dir.is_dir():
            log.error(
                "源语言目录不存在，无法继续扫描。", path=str(self.source_root_dir)
            )
            return

        for path in self.source_root_dir.rglob("*.md"):
            is_root = "root_files" in path.parts
            log.debug("发现源文件", path=str(path), is_root_file=is_root)
            yield Document(
                source_path=path.resolve(),
                source_lang=self.source_lang,
                target_langs=self.target_langs,
                is_root_file=is_root,
            )
