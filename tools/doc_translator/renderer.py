# tools/doc_translator/renderer.py
"""负责将填充了翻译结果的 Document 对象渲染成 Markdown 文件并写入磁盘。"""

import os
from pathlib import Path

import structlog

from .models import Document, LangCode

log = structlog.get_logger(__name__)


class DocRenderer:
    """文档渲染器，将 Document 对象转换为 Markdown 文件。"""

    def __init__(self, default_lang: LangCode, project_root: Path):
        self.default_lang = default_lang
        self.project_root = project_root
        self.bilingual_pair: tuple[LangCode, LangCode] = ("en", "zh")
        self.bilingual_display: dict[LangCode, str] = {
            "en": "English",
            "zh": "简体中文",
        }

    def _replace_lang_placeholder(self, content: str, lang: LangCode) -> str:
        """将内容中的 {lang} 占位符替换为指定的语言代码。"""
        return content.replace("{lang}", lang)

    def _generate_lang_switcher(self, doc: Document, current_lang: LangCode) -> str:
        """为根目录文件生成语言切换导航链接。"""
        if not doc.is_root_file:
            return ""

        links: list[str] = []
        all_langs = sorted(set([doc.source_lang] + doc.target_langs))

        lang_display_names = {
            "en": "English",
            "zh": "简体中文",
            "fr": "Français",
            "es": "Español",
            "ja": "日本語",
            "zh-CN": "简体中文",
        }

        current_doc_dir = doc.get_target_path(current_lang).parent

        for lang in all_langs:
            display_name = lang_display_names.get(lang, lang.upper())
            target_path_abs = doc.get_target_path(lang)
            relative_link_str = os.path.relpath(target_path_abs, start=current_doc_dir)

            final_link = self._replace_lang_placeholder(relative_link_str, lang)

            if lang == current_lang:
                links.append(f"**{display_name}**")
            else:
                links.append(f"[{display_name}]({final_link.replace(os.sep, '/')})")

        return " | ".join(links) + "\n\n---\n"

    def generate_single_lang_content(
        self, doc: Document, lang: LangCode, include_switcher: bool
    ) -> str:
        """根据 Document 对象，生成指定语言的完整 Markdown 内容字符串。"""
        content_parts: list[str] = []
        if include_switcher and doc.is_root_file:
            content_parts.append(self._generate_lang_switcher(doc, lang))

        for block in doc.blocks:
            block_content: str
            if block.node_type == "block_code":
                block_content = block.source_text
            else:
                block_content = block.translations.get(lang, block.source_text)

            final_block_content = self._replace_lang_placeholder(block_content, lang)
            content_parts.append(final_block_content)

        return "\n\n".join(content_parts) + "\n"

    def render_single_language_to_file(self, doc: Document, lang: LangCode) -> None:
        """将单个语言版本渲染并写入到其对应的 docs/<lang>/... 文件中。"""
        target_path = doc.get_target_path(lang)
        # 写入独立文件的版本，总是包含切换器（如果适用）
        final_content = self.generate_single_lang_content(
            doc, lang, include_switcher=True
        )
        self._write_file(target_path, final_content)

    def render_document_to_file(self, doc: Document) -> None:
        """将一个 Document 对象的所有目标语言版本渲染并写入文件。"""
        log.info("渲染文档", document=doc.name_stem, languages=doc.target_langs)
        for lang in doc.target_langs:
            self.render_single_language_to_file(doc, lang)

    def _write_file(self, path: Path, content: str) -> None:
        """将内容写入指定路径的文件，并确保目录存在。"""
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content, encoding="utf-8")
            log.debug("成功写入文件", path=str(path.relative_to(self.project_root)))
        except Exception as e:
            log.error("写入文件失败", path=str(path), error=e)
