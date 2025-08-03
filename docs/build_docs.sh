#!/bin/bash
# 文档构建脚本

# 确保脚本在错误时退出
set -e

# 清除旧的构建文件
echo "清除旧的构建文件..."
rm -rf _build

# 生成 POT 文件（用于国际化）
echo "生成 POT 文件..."
make gettext

# 构建中文文档
echo "构建中文文档..."
make html

# 复制中文文档到单独的目录
echo "复制中文文档..."
cp -r _build/html _build/html_zh

# 构建英文文档
echo "构建英文文档..."
make -e SPHINXOPTS="-D language='en'" html

# 复制英文文档到单独的目录
echo "复制英文文档..."
cp -r _build/html _build/html_en

# 重新构建中文文档作为默认文档
echo "重新构建中文文档..."
make html

# 提示用户查看文档
echo "文档构建完成！"
echo "中文文档: file://$(pwd)/_build/html/index.html"
echo "英文文档: file://$(pwd)/_build/html_en/index.html"

echo "如需添加新的语言翻译，请运行: sphinx-intl update -p _build/gettext -l <language_code>"

echo "构建脚本执行完毕。"