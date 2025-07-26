# tools/doc_translator/parser.py
import re
from dataclasses import dataclass
from hashlib import sha256


@dataclass
class TranslatableBlock:
    """代表一个从 Markdown 中提取的可翻译内容块。"""

    block_type: str  # e.g., 'paragraph', 'header', 'list_item'
    source_text: str
    stable_id: str  # 基于内容哈希的稳定ID


def parse_markdown(content: str) -> list[TranslatableBlock]:
    """
    一个智能的解析器，将 Markdown 文件内容拆分为多个可翻译的块。

    注意：这是一个简化的实现。一个生产级的解析器可能需要使用
    更强大的库（如 mistune）来处理更复杂的 Markdown 结构。
    """
    blocks = []
    # 简单的按空行分割段落
    paragraphs = re.split(r"\n{2,}", content)

    for p in paragraphs:
        p_stripped = p.strip()
        if not p_stripped:
            continue

        # 忽略代码块
        if p_stripped.startswith("```"):
            continue

        # 简单的类型判断
        block_type = "paragraph"
        if p_stripped.startswith("#"):
            block_type = "header"
        elif re.match(r"^\s*[-*+]\s|\d+\.\s", p_stripped):
            block_type = "list_item"

        # 使用内容的 sha256 哈希作为稳定 ID
        stable_id = sha256(p_stripped.encode()).hexdigest()[:16]

        blocks.append(
            TranslatableBlock(
                block_type=block_type,
                source_text=p_stripped,
                stable_id=stable_id,
            )
        )
    return blocks
