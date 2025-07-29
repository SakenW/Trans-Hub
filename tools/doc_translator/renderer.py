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

    # --- 核心变更 1: 新增占位符替换的辅助方法 ---
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

            # 对切换器中的链接也应用占位符替换
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
        """渲染并写入单个语言版本的文件。"""
        target_path = doc.get_target_path(lang)

        if doc.is_root_file and lang == self.default_lang:
            self._render_bilingual_root_file_collapsible(doc)

        content_parts: list[str] = []
        if doc.is_root_file:
            content_parts.append(self._generate_lang_switcher(doc, lang))

        for block in doc.blocks:
            block_content: str
            if block.node_type == "block_code":
                block_content = block.source_text
            else:
                block_content = block.translations.get(lang, block.source_text)

            # --- 核心变更 2: 在渲染单语文件时应用替换 ---
            final_block_content = self._replace_lang_placeholder(block_content, lang)
            content_parts.append(final_block_content)

        final_content = "\n\n".join(content_parts) + "\n"
        self._write_file(target_path, final_content)

    def _render_bilingual_root_file_collapsible(self, doc: Document) -> None:
        """为根文件生成一个可折叠、可切换的双语版本，并写入项目根目录。"""
        lang1_code, lang2_code = self.bilingual_pair
        lang1_name = self.bilingual_display[lang1_code]
        lang2_name = self.bilingual_display[lang2_code]

        lang1_content_parts: list[str] = []
        lang2_content_parts: list[str] = []
        shared_content_parts: list[str] = []
        is_last_block_shared: bool = False

        for block in doc.blocks:
            if block.node_type == "block_code":
                if not is_last_block_shared and (
                    lang1_content_parts or lang2_content_parts
                ):
                    collapsible_section = self._create_collapsible_section(
                        lang1_name, lang1_content_parts, lang2_name, lang2_content_parts
                    )
                    shared_content_parts.append(collapsible_section)
                    lang1_content_parts.clear()
                    lang2_content_parts.clear()

                # 对共享的代码块，我们使用默认语言进行占位符替换
                shared_content_parts.append(
                    self._replace_lang_placeholder(block.source_text, self.default_lang)
                )
                is_last_block_shared = True
                continue

            text_lang1 = block.translations.get(lang1_code, block.source_text)
            text_lang2 = block.translations.get(lang2_code, block.source_text)

            # --- 核心变更 3: 在渲染双语文件时，为每种语言分别应用替换 ---
            final_text_lang1 = self._replace_lang_placeholder(text_lang1, lang1_code)
            final_text_lang2 = self._replace_lang_placeholder(text_lang2, lang2_code)

            if final_text_lang1.strip() == final_text_lang2.strip():
                if not is_last_block_shared and (
                    lang1_content_parts or lang2_content_parts
                ):
                    collapsible_section = self._create_collapsible_section(
                        lang1_name, lang1_content_parts, lang2_name, lang2_content_parts
                    )
                    shared_content_parts.append(collapsible_section)
                    lang1_content_parts.clear()
                    lang2_content_parts.clear()

                shared_content_parts.append(final_text_lang1)  # 内容已替换
                is_last_block_shared = True
            else:
                lang1_content_parts.append(final_text_lang1)
                lang2_content_parts.append(final_text_lang2)
                is_last_block_shared = False

        if lang1_content_parts or lang2_content_parts:
            collapsible_section = self._create_collapsible_section(
                lang1_name, lang1_content_parts, lang2_name, lang2_content_parts
            )
            shared_content_parts.append(collapsible_section)

        header: str = (
            "<!-- This file is auto-generated. Do not edit directly. -->\n"
            "<!-- 此文件为自动生成，请勿直接编辑。 -->\n"
        )
        final_bilingual_content: str = header + "\n\n".join(shared_content_parts) + "\n"

        root_file_name = doc.get_target_path(self.default_lang).name
        root_path = self.project_root / root_file_name

        log.info(
            "同步可切换双语根文件", dest=str(root_path.relative_to(self.project_root))
        )
        self._write_file(root_path, final_bilingual_content)

    def _create_collapsible_section(
        self, name1: str, parts1: list[str], name2: str, parts2: list[str]
    ) -> str:
        """辅助函数，用于创建一个包含两种语言的可折叠HTML部分。"""
        content1 = "\n\n".join(parts1)
        content2 = "\n\n".join(parts2)

        section1 = (
            f"<details open>\n"
            f"<summary><strong>{name1}</strong></summary>\n\n"
            f"{content1}\n\n"
            f"</details>"
        )

        section2 = (
            f"<details>\n"
            f"<summary><strong>{name2}</strong></summary>\n\n"
            f"{content2}\n\n"
            f"</details>"
        )

        return f"{section1}\n\n{section2}"

    def _write_file(self, path: Path, content: str) -> None:
        """将内容写入指定路径的文件，并确保目录存在。"""
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content, encoding="utf-8")
            log.debug("成功写入文件", path=str(path.relative_to(self.project_root)))
        except Exception as e:
            log.error("写入文件失败", path=str(path), error=e)
