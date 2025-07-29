# tools/doc_translator/publisher.py
"""负责将已翻译的文档发布/同步到最终位置，例如项目根目录。"""

from pathlib import Path

import structlog

from .models import Document, LangCode
from .parser import parse_document
from .renderer import DocRenderer

log = structlog.get_logger(__name__)


class DocPublisher:
    """文档发布器，处理从 docs/ 目录到项目根目录的同步。"""

    def __init__(self, docs_dir: Path, project_root: Path, default_lang: LangCode):
        self.docs_dir = docs_dir
        self.project_root = project_root
        self.default_lang = default_lang
        # 发布器内部需要一个渲染器来执行双语渲染逻辑
        self.renderer = DocRenderer(default_lang, project_root)

    def publish_root_files(self) -> None:
        """扫描默认语言目录下的 root_files，并为它们生成双语版本发布到项目根目录。"""
        default_lang_root_files_dir = self.docs_dir / self.default_lang / "root_files"
        if not default_lang_root_files_dir.is_dir():
            log.warning(
                "默认语言的 root_files 目录不存在，跳过发布。",
                path=str(default_lang_root_files_dir),
            )
            return

        log.info("开始发布根目录文件...", source_dir=str(default_lang_root_files_dir))

        for path in default_lang_root_files_dir.glob("*.md"):
            log.debug("发现待发布的根文件", path=str(path))

            # 为了复用双语渲染逻辑，我们需要构建一个临时的 Document 对象。
            # 注意：这里的 target_langs 是为了获取双语对的另一种语言。
            # 例如，如果默认是 en，源是 zh，我们需要 en 和 zh 的翻译。
            # 这是一个简化的假设，更健壮的方案可能需要更复杂的源语言发现机制。
            # 目前，我们假设源语言是 'zh'。
            source_lang = "zh"  # TODO: 未来可以做得更动态

            # 这个 Document 只需要最基本的信息
            doc = Document(
                source_path=path,  # 路径是虚拟的，仅用于获取文件名
                source_lang=source_lang,
                target_langs=[self.default_lang],  # 包含默认语言
                is_root_file=True,
            )

            # 我们需要解析这个文件来获取其块结构
            # 注意：这里的解析是基于默认语言的已翻译文件
            parse_document(doc)

            # 现在，我们需要手动为每个块填充另一种语言的翻译
            # 我们从另一种语言的对应文件中读取内容并解析
            other_lang_code = (
                self.renderer.bilingual_pair[1]
                if self.default_lang == self.renderer.bilingual_pair[0]
                else self.renderer.bilingual_pair[0]
            )
            other_lang_path = self.docs_dir / other_lang_code / "root_files" / path.name

            if other_lang_path.exists():
                other_lang_doc = Document(
                    source_path=other_lang_path,
                    source_lang=other_lang_code,
                    target_langs=[],
                )
                parse_document(other_lang_doc)

                # 创建一个从 stable_id 到翻译文本的映射
                translation_map = {
                    block.stable_id: block.source_text
                    for block in other_lang_doc.blocks
                }

                # 填充翻译
                for block in doc.blocks:
                    if block.stable_id in translation_map:
                        block.add_translation(
                            other_lang_code, translation_map[block.stable_id]
                        )

            # 现在 doc 对象包含了两种语言的块，可以调用双语渲染了
            self.renderer._render_bilingual_page_collapsible(doc)

        log.info("根目录文件发布完成。")
