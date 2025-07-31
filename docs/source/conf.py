# Configuration file for the Sphinx documentation builder.

import os
import sys

# 将项目根目录加入 sys.path，确保 autodoc 能导入 trans_hub 模块
sys.path.insert(0, os.path.abspath("../.."))

# -- 项目信息 ----------------------------------------------------------------
project = "trans-hub"
author = "Saken"
copyright = "2025, Saken"
release = "3.0.0.dev0"

# -- 通用配置 ----------------------------------------------------------------
extensions = [
    "sphinx.ext.autodoc",  # 自动提取 docstring 生成 API 文档
    "sphinx.ext.autosectionlabel",  # 自动为章节生成标签
    "sphinx.ext.githubpages",  # 发布到 GitHub Pages 的支持
    "sphinx.ext.ifconfig",  # 支持条件内容
    "sphinx.ext.intersphinx",  # 支持交叉引用其他项目的文档
    "sphinx.ext.mathjax",  # 支持数学公式渲染
    "sphinx.ext.napoleon",  # 支持 Google 和 NumPy 风格的 docstring
    "sphinx.ext.todo",  # 支持 TODO 标记
    "sphinx.ext.viewcode",  # 显示源代码链接
    "sphinx_copybutton",  # 添加复制按钮到代码块
    "sphinx_design",  # 添加设计组件，如卡片、标签页等
    "sphinx_rtd_theme",  # Read the Docs 官方主题
    "sphinx_togglebutton",  # 添加可切换按钮
    "sphinx-prompt",  # 支持命令行提示符
    "sphinx_tabs.tabs",  # 添加标签页功能
    "sphinxcontrib.mermaid",  # 支持 Mermaid 图表
    "sphinx-intl",  # 支持国际化
]
# 自动为章节生成标签的配置
autosectionlabel_prefix_document = True

todo_include_todos = True

# sphinx_copybutton 配置
copybutton_prompt_text = "$ "
copybutton_prompt_is_regexp = False
copybutton_only_copy_prompt_lines = True

# sphinx-prompt 配置
prompt_literal_block = True

# 主题配置
html_theme_options = {
    "style_nav_header_background": "#2c3e50",
    "collapse_navigation": False,
    "sticky_navigation": True,
    "navigation_depth": 3,
}
# 模板路径
templates_path = ["_templates"]

# 排除的路径模式
exclude_patterns: list[str] = []

# 文档语言（中文）
language = "zh_CN"

# 国际化配置
locale_dirs = ["locale/"]
gettext_compact = False

# 文档源文件后缀支持：仅 .rst
source_suffix = {
    ".rst": "restructuredtext",
}

# -- HTML 输出配置 ----------------------------------------------------------
html_theme = "sphinx_rtd_theme"  # 使用 RTD 主题
html_static_path = ["_static"]  # 静态资源路径（如图片、CSS）

# -- Napoleon 扩展设置（可选） ----------------------------------------------
napoleon_google_docstring = True
napoleon_numpy_docstring = True
napoleon_include_init_with_doc = True
napoleon_include_private_with_doc = False
napoleon_use_param = True
napoleon_use_rtype = True

# -- Autodoc 设置（可选） ---------------------------------------------------
autodoc_default_options = {
    "members": True,
    "undoc-members": True,
    "private-members": False,
    "show-inheritance": True,
    "inherited-members": True,
}
