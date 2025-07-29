# tools/doc_translator/test_parser.py
"""测试 parser.py 的功能。"""

from pathlib import Path

from tools.doc_translator.models import Document
from tools.doc_translator.parser import parse_document


def test_parse_document() -> None:
    """测试 parse_document 函数。"""
    # 创建测试文件
    test_file = Path(__file__).parent / "test_doc.md"
    
    # 创建 Document 对象
    doc = Document(source_path=test_file, source_lang="zh", target_langs=["en"])
    
    # 解析文档
    parse_document(doc)
    
    # 输出解析结果
    print(f"解析出 {len(doc.blocks)} 个块:")
    for i, block in enumerate(doc.blocks, 1):
        print(f"  {i}. {block.node_type}: {block.source_text[:50]}{'...' if len(block.source_text) > 50 else ''}")


def main() -> None:
    """主函数。"""
    test_parse_document()


if __name__ == "__main__":
    main()