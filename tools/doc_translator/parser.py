# tools/doc_translator/parser.py
from dataclasses import dataclass
from hashlib import sha256
from typing import Any, List

import mistune


@dataclass
class TranslatableBlock:
    """代表一个从 Markdown 中提取的可翻译内容块。"""
    source_text: str
    stable_id: str
    node_type: str


def _extract_text_from_children(children: List[Any]) -> str:
    """[v3 核心修正] 递归地、安全地从 AST 子节点中提取并拼接所有纯文本。"""
    texts = []
    for child in children:
        if not isinstance(child, dict):
            continue
        node_type = child.get("type")
        if node_type == "text":
            texts.append(child.get("text", ""))
        if "children" in child and child["children"]:
            texts.append(_extract_text_from_children(child["children"]))
    return "".join(texts)


class TranslatableContentExtractor(mistune.BaseRenderer):
    """一个为 mistune v3 设计的渲染器，用于从 AST 中提取可翻译的文本块。"""
    NAME = "block_extractor"

    def __init__(self):
        super().__init__()
        self.blocks: List[TranslatableBlock] = []

    def __call__(self, ast: List[Any], state: Any) -> List[TranslatableBlock]:
        self.blocks = []
        for token in ast:
            node_type = token.get("type")
            if node_type in ("paragraph", "heading", "list_item"):
                full_text = _extract_text_from_children(token.get("children", [])).strip()
                if not full_text or full_text.startswith("{{") or full_text.startswith("{%"):
                    continue
                stable_id = sha256(full_text.encode()).hexdigest()
                self.blocks.append(
                    TranslatableBlock(source_text=full_text, stable_id=stable_id, node_type=node_type)
                )
        return self.blocks


def parse_markdown(content: str) -> List[TranslatableBlock]:
    """使用 mistune v3 AST 解析器来智能地提取可翻译内容。"""
    extractor = TranslatableContentExtractor()
    markdown_parser = mistune.create_markdown(renderer=extractor)
    markdown_parser(content)
    return extractor.blocks