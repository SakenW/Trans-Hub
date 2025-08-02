# docs/conf.py
# Sphinx 文档构建器的配置文件。

import os
import sys
from typing import Any

# --- 使用 setup 函数来安全地修改 sys.path ---

def setup(app: Any) -> None:
    """
    一个由 Sphinx 调用的钩子函数，用于安全地进行配置。
    我们在这里修改 sys.path，以确保 autodoc 能够找到我们的库，
    同时避免对 Sphinx 的核心路径解析产生副作用。
    """
    sys.path.insert(0, os.path.abspath(".."))
    # (可选) 未来可以在这里添加其他应用级别的配置
    # app.add_config_value(...)

# -- 项目信息 ----------------------------------------------------------------
project = "trans-hub"
author = "Saken"
copyright = "2025, Saken"
release = "3.0.0.dev0"

# -- 通用配置 ----------------------------------------------------------------

# 明确指定文档的根文件
root_doc = "index"

extensions = [
    "sphinx.ext.autodoc",
    "sphinx.ext.viewcode",
    "sphinx.ext.napoleon",
    "sphinx.ext.todo",
    "sphinx.ext.intersphinx",
    "sphinx.ext.autosectionlabel",
    "sphinx.ext.ifconfig",
    "sphinx.ext.githubpages",
    "myst_parser",  # 添加对Markdown的支持
]


# -- 国际化 (i18n) 配置 ------------------------------------------------
language = "zh_CN"
locale_dirs = ["locale/"]
gettext_compact = False

# -- 插件配置 ----------------------------------------------------------------

# Intersphinx: 链接到其他项目的文档
intersphinx_mapping = {
    "python": ("https://docs.python.org/3", None),
}

# Autosectionlabel: 自动为章节生成标签
autosectionlabel_prefix_document = True

# Todo: 在文档中显示 TODO 条目
todo_include_todos = True

# Napoleon: 解析 Google 和 NumPy 风格的 Docstring
napoleon_google_docstring = True
napoleon_numpy_docstring = True
napoleon_include_init_with_doc = True
napoleon_use_param = True
napoleon_use_rtype = True

# Autodoc: 从 Docstring 生成文档
autodoc_default_options = {
    "members": True,
    "member-order": "bysource",
    "special-members": "__init__",
    "undoc-members": False,  # 重要的优化：不包含没有 docstring 的成员
    "show-inheritance": True,
}

# -- HTML 输出配置 ----------------------------------------------------------
html_theme = "sphinx_rtd_theme"
html_static_path = ["_static"] # 确保 docs/_static 目录存在
templates_path = ["_templates"]
exclude_patterns = ["_build", "Thumbs.db", ".DS_Store"]
source_suffix = {
    '.rst': 'restructuredtext',
    '.md': 'markdown',
}

# HTML 主题选项
html_theme_options = {
    "logo_only": False,
    "prev_next_buttons_location": "bottom",
    "style_external_links": False,
    "style_nav_header_background": "#2c3e50",
    "collapse_navigation": True,
    "sticky_navigation": True,
    "navigation_depth": 4,
    "includehidden": True,
    "titles_only": False,
}
