# tools/doc_translator/models.py
"""定义文档翻译工具所需的核心数据模型。"""

from dataclasses import dataclass, field
from pathlib import Path

LangCode = str


@dataclass
class TranslatableBlock:
    """代表一个从 Markdown 中提取的可翻译内容块。"""

    source_text: str
    stable_id: str
    node_type: str
    translations: dict[LangCode, str] = field(default_factory=dict)

    @property
    def business_id(self) -> str:
        """为 Trans-Hub 提供一个全局唯一的业务ID。"""
        return self.stable_id

    def add_translation(self, lang: LangCode, text: str) -> None:
        """为指定的语言添加或更新翻译文本。"""
        self.translations[lang] = text


@dataclass
class Document:
    """代表一个完整的 Markdown 文档。"""

    source_path: Path
    source_lang: LangCode
    target_langs: list[LangCode]
    is_root_file: bool = False
    blocks: list[TranslatableBlock] = field(default_factory=list)

    @property
    def name_stem(self) -> str:
        """获取不带扩展名的文件名主干。例如 '01_quickstart'。"""
        return self.source_path.stem

    def get_target_path(self, lang: LangCode) -> Path:
        """
        根据目标语言计算输出文件的路径。
        例如: docs/zh/guides/a.md -> docs/en/guides/a.md
        """
        parts = list(self.source_path.parts)
        # 找到语言代码在路径中的位置并替换
        try:
            lang_index = parts.index(self.source_lang)
            parts[lang_index] = lang
            return Path(*parts)
        except ValueError:
            # 如果路径中找不到源语言代码，返回一个错误或默认路径
            # 这种情况在我们的扫描逻辑下不应该发生
            return self.source_path.with_suffix(f".{lang}.md")
