# Configuration file for the Sphinx documentation builder.

import os
import sys

# 将项目根目录加入 sys.path，确保 autodoc 能导入 trans_hub 模块
sys.path.insert(0, os.path.abspath('../..'))

# -- 项目信息 ----------------------------------------------------------------
project = 'trans-hub'
author = 'Saken'
copyright = '2025, Saken'
release = '3.0.0.dev0'

# -- 通用配置 ----------------------------------------------------------------
extensions = [
    'sphinx.ext.autodoc',          # 自动提取 docstring 生成 API 文档
    'sphinx.ext.napoleon',         # 支持 Google 和 NumPy 风格的 docstring
    'sphinx_rtd_theme',            # Read the Docs 官方主题
]

# 模板路径
templates_path = ['_templates']

# 排除的路径模式
exclude_patterns = []

# 文档语言（中文）
language = 'zh_CN'

# 文档源文件后缀支持：仅 .rst
source_suffix = {
    '.rst': 'restructuredtext',
}

# -- HTML 输出配置 ----------------------------------------------------------
html_theme = 'sphinx_rtd_theme'   # 使用 RTD 主题
html_static_path = ['_static']    # 静态资源路径（如图片、CSS）

# -- Napoleon 扩展设置（可选） ----------------------------------------------
napoleon_google_docstring = True
napoleon_numpy_docstring = True
napoleon_include_init_with_doc = True
napoleon_include_private_with_doc = False
napoleon_use_param = True
napoleon_use_rtype = True

# -- Autodoc 设置（可选） ---------------------------------------------------
autodoc_default_options = {
    'members': True,
    'undoc-members': True,
    'private-members': False,
    'show-inheritance': True,
    'inherited-members': True,
}