.. # docs/guides/multilingual_support.rst

======================
多语言文档贡献指南
======================

`Trans-Hub` 项目的文档支持多语言，使用 Sphinx 的国际化 (i18n) 功能实现，并由 **Read the Docs** 平台全自动构建和托管。本指南将介绍如何为文档贡献新的翻译。

我们的主语言是**中文 (`zh_CN`)**。所有 `.rst` 和 `.md` 文件都应首先使用中文编写。

工作流程概述
------------

1. **提取原文**: 将中文源文件中的可翻译文本提取到模板文件 (`.pot`)。
2. **更新翻译文件**: 为目标语言（如英语 `en`）创建或更新翻译文件 (`.po`)。
3. **翻译内容**: 编辑 `.po` 文件，填入译文。
4. **提交变更**: 将修改后的 `.po` 文件提交到 GitHub。
5. **自动部署**: Read the Docs 会自动检测到变更，并为该语言构建和部署更新后的文档。

本地操作步骤
------------

以下所有命令都在 `docs/` 目录下执行。

### 第一步：提取原文

当您修改了任何 `.rst` 或 `.md` 源文件后，需要更新翻译模板。我们已为此提供了便捷的 Makefile 命令。

.. code-block:: shell
   :caption: 在 docs/ 目录下运行

   make gettext

此命令会扫描所有源文件，并在 `docs/_build/gettext/` 目录下生成或更新 `.pot` 模板文件。

### 第二步：更新目标语言的翻译文件

接下来，使用 `sphinx-intl` 工具更新特定语言的翻译文件（`.po`）。我们同样为此提供了 Makefile 快捷方式。

.. code-block:: shell
   :caption: 示例：更新英语 (en) 的翻译文件

   make update-po-en

如果您想添加一种全新的语言（例如，法语 `fr`），可以手动运行 `sphinx-intl` 命令，然后为它创建一个 Makefile 快捷方式。

.. code-block:: shell

   sphinx-intl update -p _build/gettext -l fr

此命令会在 `docs/locale/fr/LC_messages/` 目录下创建所有必需的 `.po` 文件。

### 第三步：翻译 `.po` 文件

使用您喜欢的文本编辑器或专业的 PO 文件编辑器（如 `Poedit`）打开目标语言目录下的 `.po` 文件。

您会看到成对的文本块：

.. code-block:: po

   #: ../../docs/configuration.rst:11
   msgid "Configuration loading order"
   msgstr ""

- ``msgid``: 这是需要翻译的中文原文。
- ``msgstr``: 在这里填入您的译文。

.. code-block:: po

   #: ../../docs/configuration.rst:11
   msgid "Configuration loading order"
   msgstr "配置加载顺序"

完成翻译后，保存文件。

### 第四步（可选）：本地预览

如果您想在提交前预览翻译效果，可以构建特定语言的文档。

.. code-block:: shell
   :caption: 示例：构建并预览英文文档

   make -e SPHINXOPTS="-D language=en" html

构建成功后，在浏览器中打开 `docs/_build/html/index.html` 即可预览。

自动化部署
----------

您**不需要**手动构建所有语言的文档或配置语言切换器。

- **自动构建**: 当您将更新后的 `.po` 文件推送到 GitHub 仓库后，Read the Docs 会自动为每个已配置的语言版本触发一次新的构建。
- **自动语言切换器**: Read the Docs 会在您文档网站的右下角**自动注入一个浮动的语言和版本切换器**，用户可以通过它在中文、英文等不同语言版本之间自由切换。

.. image:: https://docs.readthedocs.io/en/stable/_images/flyout-menu.png
   :alt: Read the Docs 语言切换器示例
   :align: center
   :width: 300px

因此，您作为翻译贡献者的工作，在**提交 `.po` 文件**后即告完成。

最佳实践
--------

- **保持一致性**: 尽量保持术语翻译在整个文档中的一致性。
- **提交完整性**: 在提交代码时，请同时提交您修改过的 `.po` 文件。
- **定期同步**: 定期运行 `make gettext` 和 `make update-po-<lang>`，以确保您的翻译文件与最新的中文原文保持同步。