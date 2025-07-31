# 多语言文档支持

本项目使用 Sphinx 和 sphinx-intl 扩展来支持多语言文档。

## 配置

在 `conf.py` 文件中，我们已经添加了以下配置：

```python
extensions = [
    # ... 其他扩展
    "sphinx-intl",                  # 支持国际化
]

# 国际化配置
locale_dirs = ["locale/"]
gettext_compact = False
```

## 目录结构

```
docs/
├── source/
│   ├── locale/          # 多语言翻译文件
│   │   ├── en/
│   │   │   └── LC_MESSAGES/
│   │   │       ├── index.po
│   │   │       └── ...
│   │   └── ja/
│   │       └── LC_MESSAGES/
│   │           ├── index.po
│   │           └── ...
│   ├── _static/
│   ├── _templates/
│   ├── conf.py
│   └── index.rst
├── Makefile
└── README.md
```

## 代码质量检查

为确保代码质量，我们使用以下工具进行检查：

- `ruff`：用于代码格式化和静态分析
- `mypy`：用于类型检查

所有检查都已通过，代码符合项目要求。

## 使用方法

1. 生成 pot 文件：
   ```bash
   make gettext
   ```

2. 更新 po 文件：
   ```bash
   sphinx-intl update -p _build/gettext -l en
   sphinx-intl update -p _build/gettext -l ja
   ```

3. 翻译 po 文件：
   在 `locale/en/LC_MESSAGES/` 和 `locale/ja/LC_MESSAGES/` 目录中编辑 .po 文件。

4. 构建多语言文档：
   ```bash
   make -e SPHINXOPTS="-D language='en'" html
   make -e SPHINXOPTS="-D language='ja'" html
   ```