# tools/doc_translator/parser.py
"""负责将 Markdown 文件内容解析为可翻译的文本块列表。"""

from collections.abc import Iterable
from hashlib import sha256
from pathlib import Path
from typing import Any, cast

import mistune
import structlog

from .models import Document, TranslatableBlock

log = structlog.get_logger(__name__)


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


class ContentExtractor(mistune.BaseRenderer):
    """一个为 mistune v3 设计的渲染器，用于从 AST 中递归提取可翻译和不可翻译的块。"""

    NAME = "content_extractor"

    def __init__(self) -> None:
        super().__init__()
        self.blocks: list[TranslatableBlock] = []
        self.counter = 0

    def __call__(self, ast: Iterable[dict[str, Any]], state: Any) -> str:
        """Mistune v3 调用入口。"""
        self.blocks = []
        self.counter = 0

        # 从顶层节点开始递归遍历
        for token in ast:
            self._recursive_render_token(token, state)

        return ""

    def _recursive_render_token(self, token: dict[str, Any], state: Any) -> None:
        """递归地遍历 AST 树，提取所有内容块。"""
        node_type = token.get("type")

        # 我们关心的可翻译块类型
        translatable_types = ("paragraph", "heading", "list_item")

        if node_type in translatable_types:
            children_list = cast(list[dict[str, Any]], token.get("children", []))
            full_text = _extract_text_from_children(children_list).strip()

            if (
                full_text
                and not full_text.startswith("{{")
                and not full_text.startswith("{%")
            ):
                stable_id = sha256(full_text.encode("utf-8")).hexdigest()
                self.blocks.append(
                    TranslatableBlock(
                        source_text=full_text, stable_id=stable_id, node_type=node_type
                    )
                )
        elif node_type == "block_code":
            self.counter += 1
            stable_id = f"code_block_{self.counter:03d}"
            code_text = token.get("raw", "")
            if code_text:
                self.blocks.append(
                    TranslatableBlock(
                        source_text=code_text,
                        stable_id=stable_id,
                        node_type=node_type,
                    )
                )

        # --- 核心修正：递归进入子节点 ---
        # 无论当前节点是否被处理，我们都要继续深入其子节点
        children = token.get("children")
        if children and isinstance(children, list):
            for child in children:
                if isinstance(child, dict):
                    # 对每一个子节点，都调用这个递归函数
                    self._recursive_render_token(child, state)


def parse_document(doc: Document) -> None:
    """解析一个 Document 对象中的源文件，并将解析出的块填充回 Document 对象。"""
    log.info("正在解析文件", path=str(doc.source_path.relative_to(Path.cwd())))
    try:
        content = doc.source_path.read_text("utf-8")
        extractor = ContentExtractor()
        markdown_parser = mistune.create_markdown(renderer=extractor)
        markdown_parser(content)

        doc.blocks = extractor.blocks

        log.info("解析成功", file=doc.source_path.name, block_count=len(doc.blocks))
    except Exception as e:
        log.error("解析 Markdown 文件失败", path=str(doc.source_path), error=e)
        doc.blocks = []
