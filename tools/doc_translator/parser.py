# tools/doc_translator/parser.py
"""负责将 Markdown 文件内容解析为可翻译的文本块列表。"""

from hashlib import sha256
from pathlib import Path

from markdown_it import MarkdownIt
import structlog

from .models import Document, TranslatableBlock

log = structlog.get_logger(__name__)


def parse_document(doc: Document) -> None:
    """
    解析一个 Document 对象中的源文件，并将解析出的块填充回 Document 对象。

    本解析器采用“分块”策略，以确保 Markdown 结构在翻译前后保持一致：
    1.  使用 markdown-it-py 将整个文档解析成 token 流。
    2.  遍历 token 流，将顶层元素（如标题、段落、列表、代码块）识别为独立的块。
    3.  利用 token 的 `map` 属性（行号范围）从原始文件中精确提取每个块的完整 Markdown 源码。
    4.  每个块（`TranslatableBlock`）的 `source_text` 都存储着这段完整的、包含语法的源码。
       - 对于代码块，`node_type` 设为 'block_code'，翻译时将被跳过。
       - 对于其他文本块，其 `source_text`（例如 "### My Title" 或 "* List item"）将被直接发送给翻译引擎。
         我们依赖翻译引擎（如 GPT-4）的能力来理解并保留这些 Markdown 语法。
    """
    log.info("正在解析文件", path=str(doc.source_path.relative_to(Path.cwd())))
    try:
        content = doc.source_path.read_text("utf-8")
        lines = content.splitlines(keepends=True)
        if not lines:
            log.warning("文件内容为空，跳过解析", path=str(doc.source_path))
            doc.blocks = []
            return

        md = MarkdownIt()
        tokens = md.parse(content)
        blocks: list[TranslatableBlock] = []

        i = 0
        while i < len(tokens):
            token = tokens[i]

            # --- 核心修正 1：增加防御性检查 ---
            # 如果 token 没有 map（行号信息），或者不是 level 0 的块级 token，直接跳过。
            # 这是处理 TypeError 的根本方法。
            if not token.map or not token.block or token.level != 0:
                i += 1
                continue

            start_line, map_end_line = token.map
            
            end_token_idx = i
            if token.nesting == 1:
                nesting_level = 1
                for j in range(i + 1, len(tokens)):
                    if tokens[j].level == token.level:
                        nesting_level += tokens[j].nesting
                    if nesting_level == 0:
                        end_token_idx = j
                        break
            
            # --- 核心修正 2：确保结束 token 也有 map ---
            # 有时结束 token 可能也没有 map，需要做安全检查
            end_token = tokens[end_token_idx]
            if not end_token.map:
                 # 如果结束 token 没有 map，这是一个异常情况，我们保守地使用开始 token 的 map
                 end_line = map_end_line
            else:
                 end_line = end_token.map[1]

            block_content = "".join(lines[start_line:end_line]).strip()

            if not block_content:
                i = end_token_idx + 1
                continue

            is_code_or_html = token.type in ("fence", "code_block", "html_block")
            node_type = token.type.replace("_open", "") if not is_code_or_html else "block_code"

            if node_type == "hr":
                 i = end_token_idx + 1
                 continue

            stable_id = sha256(block_content.encode("utf-8")).hexdigest()
            blocks.append(
                TranslatableBlock(
                    source_text=block_content,
                    stable_id=stable_id,
                    node_type=node_type,
                )
            )

            i = end_token_idx + 1

        doc.blocks = blocks
        log.info("解析成功", file=doc.source_path.name, block_count=len(doc.blocks))

    except Exception:
        # 保持异常捕获，以防其他未知错误
        log.exception("解析 Markdown 文件失败", path=str(doc.source_path))
        doc.blocks = []