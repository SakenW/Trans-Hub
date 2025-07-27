# tools/doc_translator/renderer.py
"""负责将填充了翻译结果的 Document 对象渲染成 Markdown 文件并写入磁盘。"""

from pathlib import Path

import structlog

from .models import Document, LangCode

log = structlog.get_logger(__name__)


class DocRenderer:
    """文档渲染器，将 Document 对象转换为 Markdown 文件。"""

    def __init__(self, default_lang: LangCode, project_root: Path):
        self.default_lang = default_lang
        self.project_root = project_root

    def _generate_lang_switcher(self, doc: Document, current_lang: LangCode) -> str:
        """为根目录文件生成语言切换导航链接。"""
        if not doc.is_root_file:
            return ""

        links = []
        all_langs = sorted(set([doc.source_lang] + doc.target_langs))

        lang_display_names = {
            "en": "English",
            "zh": "简体中文",
            "fr": "Français",
            "es": "Español",
            "ja": "日本語",
        }
        lang_display_names.update({"zh-CN": "简体中文"})

        for lang in all_langs:
            display_name = lang_display_names.get(lang, lang)

            # 链接始终指向 docs/<lang>/root_files/...
            target_doc_path = doc.get_target_path(lang)
            target_doc_path.relative_to(self.project_root)

            # 对于默认语言，当从根目录访问时，链接也应指向 docs 内
            if lang == self.default_lang and current_lang == self.default_lang:
                pass
            else:
                pass

            # 简化链接逻辑，所有链接都从项目根目录的角度出发
            final_link_path = str(target_doc_path.relative_to(self.project_root))

            if lang == current_lang:
                links.append(f"**{display_name}**")
            else:
                links.append(f"[{display_name}]({final_link_path})")

        return " | ".join(links) + "\n\n---\n"

    def render_document_to_file(self, doc: Document) -> None:
        """将一个 Document 对象的所有目标语言版本渲染并写入文件。"""
        log.info("正在渲染文档", document=doc.name_stem, languages=doc.target_langs)

        for lang in doc.target_langs:
            self.render_single_language(doc, lang)

    def render_single_language(self, doc: Document, lang: LangCode) -> None:
        """渲染并写入单个语言版本的文件。"""
        target_path = doc.get_target_path(lang)

        content_parts = []
        is_default_lang_root_file = doc.is_root_file and lang == self.default_lang

        if doc.is_root_file:
            content_parts.append(self._generate_lang_switcher(doc, lang))

        for block in doc.blocks:
            if block.node_type == "block_code":
                content_parts.append(block.source_text)
            else:
                translated_text = block.translations.get(lang, block.source_text)
                content_parts.append(translated_text)

        final_content = "\n\n".join(content_parts) + "\n"

        # 如果是根目录文件的默认语言版本，需要额外写入到项目根目录
        if is_default_lang_root_file:
            root_path = self.project_root / target_path.name
            log.info(
                "同步根文件",
                source=str(target_path.relative_to(self.project_root)),
                dest=str(root_path),
            )
            self._write_file(root_path, final_content)

        # 始终写入到 docs/<lang>/... 目录下
        self._write_file(target_path, final_content)

    def _write_file(self, path: Path, content: str) -> None:
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content, encoding="utf-8")
            log.debug("成功写入文件", path=str(path))
        except Exception as e:
            log.error("写入文件失败", path=str(path), error=e)
