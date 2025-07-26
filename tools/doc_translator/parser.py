# tools/doc_translator/parser.py
from collections.abc import Iterable
from dataclasses import dataclass
from hashlib import sha256
from typing import Any

import mistune


@dataclass
class TranslatableBlock:
    """代表一个从 Markdown 中提取的可翻译内容块。"""

    source_text: str
    stable_id: str
    node_type: str


def _extract_text_from_children(children: list[Any]) -> str:
    """递归地、安全地从 AST 子节点中提取并拼接所有纯文本。"""
    texts = []
    for child in children:
        if not isinstance(child, dict):
            continue
        node_type = child.get("type")
        if node_type == "text":
            texts.append(child.get("text", ""))
        children_list = child.get("children")
        if children_list and isinstance(children_list, list):
            texts.append(_extract_text_from_children(children_list))
    return "".join(texts)


class TranslatableContentExtractor(mistune.BaseRenderer):
    """一个为 mistune v3 设计的渲染器，用于从 AST 中提取可翻译的文本块。"""

    NAME = "block_extractor"

    def __init__(self):
        super().__init__()
        self.blocks: list[TranslatableBlock] = []

    def __call__(self, ast: Iterable[dict[str, Any]], state: Any) -> str:
        self.blocks = []
        for token in ast:
            node_type = token.get("type")
            if node_type in ("paragraph", "heading", "list_item"):
                children_list = token.get("children", [])
                full_text = _extract_text_from_children(children_list).strip()
                if (
                    not full_text
                    or full_text.startswith("{{")
                    or full_text.startswith("{%")
                ):
                    continue
                stable_id = sha256(full_text.encode()).hexdigest()
                self.blocks.append(
                    TranslatableBlock(
                        source_text=full_text, stable_id=stable_id, node_type=node_type
                    )
                )
        # [关键] 必须返回一个字符串，以遵守父类约定
        return ""


def parse_markdown(content: str) -> list[TranslatableBlock]:
    """使用 mistune v3 AST 解析器来智能地提取可翻译内容。"""
    extractor = TranslatableContentExtractor()
    markdown_parser = mistune.create_markdown(renderer=extractor)
    markdown_parser(content)
    return extractor.blocks
