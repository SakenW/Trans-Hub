# tools/doc_translator/publisher.py
"""负责将已翻译的文档发布/同步到最终位置，例如项目根目录。"""

from pathlib import Path
from typing import Optional

import structlog

from .models import Document, LangCode
from .parser import parse_document
from .renderer import DocRenderer

log = structlog.get_logger(__name__)


class DocPublisher:
    """文档发布器，处理从 docs/ 目录到项目根目录的同步。"""

    def __init__(self, docs_dir: Path, project_root: Path, default_lang: LangCode):
        self.docs_dir = docs_dir
        self.project_root = project_root
        self.default_lang = default_lang
        # 发布器内部需要一个渲染器来执行内容生成
        self.renderer = DocRenderer(default_lang, project_root)

    def publish_root_files(self) -> None:
        """
        扫描默认语言目录下的 root_files，并为它们生成双语版本发布到项目根目录。
        """
        default_lang_root_files_dir = self.docs_dir / self.default_lang / "root_files"
        if not default_lang_root_files_dir.is_dir():
            log.warning(
                "默认语言的 root_files 目录不存在，跳过发布。",
                path=str(default_lang_root_files_dir)
            )
            return

        log.info("开始发布根目录文件...", source_dir=str(default_lang_root_files_dir.relative_to(self.project_root)))

        for path in default_lang_root_files_dir.glob("*.md"):
            log.debug("正在处理根文件", path=path.name)
            
            lang1_code, lang2_code = self.renderer.bilingual_pair
            lang1_name = self.renderer.bilingual_display.get(lang1_code, lang1_code)
            lang2_name = self.renderer.bilingual_display.get(lang2_code, lang2_code)
            
            # 确保 lang1 是我们的 default_lang，以便默认展开
            if lang1_code != self.default_lang:
                lang1_code, lang2_code = lang2_code, lang1_code
                lang1_name, lang2_name = lang2_name, lang1_name

            # 1. 为第一种语言（默认语言）构建 Document 并获取纯净内容
            doc_lang1 = self._build_doc_for_lang(lang1_code, path.name)
            if not doc_lang1:
                continue
            content_lang1 = self.renderer.generate_single_lang_content(
                doc_lang1, lang1_code, include_switcher=False
            )

            # 2. 为第二种语言构建 Document 并获取纯净内容
            doc_lang2 = self._build_doc_for_lang(lang2_code, path.name)
            if not doc_lang2:
                # 如果第二语言文件不存在，只发布第一语言的文件
                log.warning("未找到对应的第二语言文件，将只发布单语版本。", filename=path.name, lang=lang2_code)
                content_lang2 = ""
            else:
                 content_lang2 = self.renderer.generate_single_lang_content(
                    doc_lang2, lang2_code, include_switcher=False
                )
            
            # 3. 组装最终的 HTML
            header = "<!-- This file is auto-generated. Do not edit directly. -->\n<!-- 此文件为自动生成，请勿直接编辑。 -->\n"
            
            if content_lang2:
                section1 = f"<details open>\n<summary><strong>{lang1_name}</strong></summary>\n\n{content_lang1}\n</details>"
                section2 = f"<details>\n<summary><strong>{lang2_name}</strong></summary>\n\n{content_lang2}\n</details>"
                final_content = f"{header}\n{section1}\n\n{section2}\n"
            else:
                final_content = f"{header}\n{content_lang1}"


            # 4. 写入根目录
            root_path = self.project_root / path.name
            log.info("同步页面级可切换双语根文件", dest=str(root_path.relative_to(self.project_root)))
            self.renderer._write_file(root_path, final_content)

        log.info("根目录文件发布完成。")
        
    def _build_doc_for_lang(self, lang: LangCode, filename: str) -> Optional[Document]:
        """辅助函数，为指定语言和文件名加载和解析文档。"""
        file_path = self.docs_dir / lang / "root_files" / filename
        if not file_path.exists():
            log.warning(f"在发布时未找到对应的语言文件，跳过", lang=lang, filename=filename)
            return None
        
        doc = Document(source_path=file_path, source_lang=lang, target_langs=[], is_root_file=True)
        parse_document(doc)
        # 为文档本身填充“翻译”（即原文），以便渲染器能找到内容
        for block in doc.blocks:
            block.add_translation(lang, block.source_text)
        return doc