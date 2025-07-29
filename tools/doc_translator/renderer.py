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
        # --- 核心变更 1: 定义双语渲染的语言对 ---
        # 可以将其变为可配置项，但目前硬编码为 'en' 和 'zh'
        self.bilingual_pair: tuple[LangCode, LangCode] = ("en", "zh")

    def _generate_lang_switcher(self, doc: Document, current_lang: LangCode) -> str:
        """为根目录文件生成语言切换导航链接。"""
        if not doc.is_root_file:
            return ""

        links = []
        all_langs = sorted(set([doc.source_lang] + doc.target_langs))

        lang_display_names = {
            "en": "English", "zh": "简体中文", "fr": "Français",
            "es": "Español", "ja": "日本語", "zh-CN": "简体中文",
        }

        current_doc_dir = doc.get_target_path(current_lang).parent

        for lang in all_langs:
            display_name = lang_display_names.get(lang, lang.upper())
            target_path_abs = doc.get_target_path(lang)
            relative_link_str = os.path.relpath(target_path_abs, start=current_doc_dir)

            if lang == current_lang:
                links.append(f"**{display_name}**")
            else:
                links.append(f"[{display_name}]({relative_link_str.replace(os.sep, '/')})")

        return " | ".join(links) + "\n\n---\n"

    def render_document_to_file(self, doc: Document) -> None:
        """将一个 Document 对象的所有目标语言版本渲染并写入文件。"""
        log.info("正在渲染文档", document=doc.name_stem, languages=doc.target_langs)

        for lang in doc.target_langs:
            self.render_single_language(doc, lang)

    def render_single_language(self, doc: Document, lang: LangCode) -> None:
        """渲染并写入单个语言版本的文件。"""
        target_path = doc.get_target_path(lang)

        # --- 核心变更 2: 修改根文件处理逻辑 ---
        # 仅当渲染的语言是项目的默认语言时，才触发根文件的特殊处理
        if doc.is_root_file and lang == self.default_lang:
            self._render_bilingual_root_file(doc)

        # 始终为每种目标语言生成其单语种的文档，存放在 docs/<lang>/... 目录下
        content_parts = []
        if doc.is_root_file:
            content_parts.append(self._generate_lang_switcher(doc, lang))

        for block in doc.blocks:
            if block.node_type == "block_code":
                content_parts.append(block.source_text)
            else:
                translated_text = block.translations.get(lang, block.source_text)
                content_parts.append(translated_text)
        
        final_content = "\n\n".join(content_parts) + "\n"
        self._write_file(target_path, final_content)

    # --- 核心变更 3: 新增双语渲染的私有方法 ---
    def _render_bilingual_root_file(self, doc: Document) -> None:
        """
        为根文件生成一个双语版本并写入项目根目录。
        例如，将英文和中文内容合并到一个 README.md 文件中。
        """
        lang1_code, lang2_code = self.bilingual_pair
        lang1_name = "English"
        lang2_name = "简体中文"

        bilingual_parts = []
        # 添加一个头部说明
        bilingual_parts.append(
            f"<!-- This file is auto-generated. Do not edit directly. -->\n"
            f"<!-- 此文件为自动生成，请勿直接编辑。 -->\n"
        )
        
        for block in doc.blocks:
            # 代码块是共享的，不分语言，直接添加
            if block.node_type == "block_code":
                bilingual_parts.append(block.source_text)
                continue

            # 获取两种语言的翻译，如果不存在则回退到原文
            text_lang1 = block.translations.get(lang1_code, block.source_text)
            text_lang2 = block.translations.get(lang2_code, block.source_text)
            
            # 如果两种语言的内容相同（例如，只有链接或未翻译），则只显示一次
            if text_lang1.strip() == text_lang2.strip():
                bilingual_parts.append(text_lang1)
            else:
                # 添加带有注释的版本
                bilingual_parts.append(f"<!-- {lang1_name} -->\n{text_lang1}")
                bilingual_parts.append(f"<!-- {lang2_name} -->\n{text_lang2}")
                # 在不同语言的文本块之间添加分隔符，以提高可读性
                bilingual_parts.append("---\n")
        
        # 移除最后一个多余的分隔符
        if bilingual_parts and bilingual_parts[-1].strip() == '---':
            bilingual_parts.pop()

        final_bilingual_content = "\n\n".join(bilingual_parts) + "\n"
        
        # 计算根目录的目标路径
        # 我们使用默认语言的路径来获取文件名
        root_file_name = doc.get_target_path(self.default_lang).name
        root_path = self.project_root / root_file_name

        log.info(
            "同步双语根文件",
            dest=str(root_path.relative_to(self.project_root)),
        )
        self._write_file(root_path, final_bilingual_content)


    def _write_file(self, path: Path, content: str) -> None:
        """将内容写入指定路径的文件，并确保目录存在。"""
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content, encoding="utf-8")
            log.debug("成功写入文件", path=str(path.relative_to(self.project_root)))
        except Exception as e:
            log.error("写入文件失败", path=str(path), error=e)