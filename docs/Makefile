# docs/Makefile
# 为 Sphinx 文档定制的 Makefile。
# 经过优化，以支持扁平化的目录结构（无 "source" 子目录）。

# 您可以从命令行设置这些变量。
SPHINXOPTS    ?=
SPHINXBUILD   ?= sphinx-build
# --- 核心优化：源目录就是当前目录 (.) ---
SOURCEDIR     = .
# 构建产物目录
BUILDDIR      = _build

# 将 help 置于首位，因此不带参数的 "make" 会显示帮助信息。
help:
	@$(SPHINXBUILD) -M help "$(SOURCEDIR)" "$(BUILDDIR)" $(SPHINXOPTS) $(O)

.PHONY: help Makefile

# i18n/l10n 快捷命令
# 提取原文到 .pot 文件
gettext:
	@$(SPHINXBUILD) -M gettext "$(SOURCEDIR)" "$(BUILDDIR)" $(SPHINXOPTS)

# 更新指定语言的 .po 文件 (例如: make update-po-en)
update-po-%:
	@sphinx-intl update -p "$(BUILDDIR)/gettext" -l $*

# 捕获所有未知目标：使用 Sphinx 的“make 模式”选项路由所有命令。
# $(O) 是 $(SPHINXOPTS) 的快捷方式。
%: Makefile
	@$(SPHINXBUILD) -M $@ "$(SOURCEDIR)" "$(BUILDDIR)" $(SPHINXOPTS) $(O)