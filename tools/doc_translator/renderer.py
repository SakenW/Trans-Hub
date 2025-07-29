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
        return content.replace("{lang}", lang)

    def _generate_lang_switcher(self, doc: Document, current_lang: LangCode) -> str:
        # ... (此方法保持不变)
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

    def render_document_to_file(self, doc: Document) -> None:
        """将一个 Document 对象的所有目标语言版本渲染并写入文件。"""
        log.info("正在渲染文档", document=doc.name_stem, languages=doc.target_langs)
        for lang in doc.target_langs:
            self.render_single_language(doc, lang)

    def render_single_language(self, doc: Document, lang: LangCode) -> None:
        """渲染并写入单个语言版本的文件到 docs/<lang>/... 目录。"""
        target_path = doc.get_target_path(lang)

        # --- 核心变更：移除所有根文件同步逻辑 ---
        # is_default_lang_root_file 变量和相关的 if 判断被移除。
        # 此方法现在只负责生成单语文件。

        content_parts: list[str] = []
        if doc.is_root_file:
            content_parts.append(self._generate_lang_switcher(doc, lang))

        for block in doc.blocks:
            block_content: str
            if block.node_type == "block_code":
                block_content = block.source_text
            else:
                block_content = block.translations.get(lang, block.source_text)

            final_block_content = self._replace_lang_placeholder(block_content, lang)
            content_parts.append(final_block_content)

        final_content = "\n\n".join(content_parts) + "\n"
        self._write_file(target_path, final_content)

    def _render_bilingual_page_collapsible(self, doc: Document) -> None:
        """为根文件生成一个页面级的、可切换的双语版本，并写入项目根目录。"""
        # ... (此方法保持不变，但现在由 Publisher 调用)
        lang1_code, lang2_code = self.bilingual_pair
        lang1_name = self.bilingual_display[lang1_code]
        lang2_name = self.bilingual_display[lang2_code]
        lang1_parts: list[str] = []
        lang2_parts: list[str] = []
        for block in doc.blocks:
            if block.node_type == "block_code":
                content = self._replace_lang_placeholder(
                    block.source_text, self.default_lang
                )
                lang1_parts.append(content)
                lang2_parts.append(content)
                continue
            text_lang1 = block.translations.get(lang1_code, block.source_text)
            final_text_lang1 = self._replace_lang_placeholder(text_lang1, lang1_code)
            lang1_parts.append(final_text_lang1)
            text_lang2 = block.translations.get(lang2_code, block.source_text)
            final_text_lang2 = self._replace_lang_placeholder(text_lang2, lang2_code)
            lang2_parts.append(final_text_lang2)
        full_content_lang1 = "\n\n".join(lang1_parts)
        full_content_lang2 = "\n\n".join(lang2_parts)
        section1 = f"<details open>\n<summary><strong>{lang1_name}</strong></summary>\n\n{full_content_lang1}\n\n</details>"
        section2 = f"<details>\n<summary><strong>{lang2_name}</strong></summary>\n\n{full_content_lang2}\n\n</details>"
        header = "<!-- This file is auto-generated. Do not edit directly. -->\n<!-- 此文件为自动生成，请勿直接编辑。 -->\n"
        final_bilingual_content = f"{header}\n{section1}\n\n{section2}\n"
        root_file_name = doc.source_path.name  # 使用 source_path 的 name
        root_path = self.project_root / root_file_name
        log.info(
            "同步页面级可切换双语根文件",
            dest=str(root_path.relative_to(self.project_root)),
        )
        self._write_file(root_path, final_bilingual_content)

    def _write_file(self, path: Path, content: str) -> None:
        # ... (此方法保持不变)
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content, encoding="utf-8")
            log.debug("成功写入文件", path=str(path.relative_to(self.project_root)))
        except Exception as e:
            log.error("写入文件失败", path=str(path), error=e)
