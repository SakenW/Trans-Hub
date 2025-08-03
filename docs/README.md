<!-- docs/README.md -->
# Trans-Hub

`Trans-Hub` 是一个功能强大、灵活可扩展的翻译协调系统，旨在简化多引擎翻译工作流，提供统一的 API 接口和丰富的功能集。

## 核心特性

- **多引擎支持**：集成多种翻译引擎，包括 OpenAI、Google Translate 等
- **统一 API**：提供一致的接口，简化翻译请求的发送和结果处理
- **智能缓存**：自动缓存翻译结果，提高性能并降低成本
- **异步处理**：基于 Python asyncio 实现高效的异步翻译处理
- **灵活配置**：支持多种配置方式，适应不同的使用场景
- **可扩展性**：易于添加新的翻译引擎和自定义功能
- **完整的生命周期管理**：跟踪翻译请求的整个生命周期
- **强大的命令行工具**：提供便捷的管理和操作界面

## 快速上手

### 安装

```bash
# 使用 pip 安装
pip install trans-hub

# 或从源码安装
git clone https://github.com/your-org/trans-hub.git
cd trans-hub
pip install -e .
```

### 基本使用

```python
import asyncio
from trans_hub.coordinator import Coordinator
from trans_hub.config import TransHubConfig

async def main():
    # 创建配置
    config = TransHubConfig(
        active_engine="debug",
        database_url="sqlite:///trans_hub.db"
    )

    # 初始化协调器
    coordinator = Coordinator(config)
    await coordinator.initialize()

    # 请求翻译
    result = await coordinator.request_translation(
        business_id="example.hello",
        text="你好世界",
        target_lang="en"
    )

    print(f"翻译结果: {result}")

    # 关闭协调器
    await coordinator.close()

# 运行主函数
asyncio.run(main())
```

### 启动 Worker

```bash
# 使用命令行工具启动 Worker
th worker
```

## 文档

- **API 文档**: [API Reference](api/index.rst)
- **架构文档**: [Architecture Overview](guides/architecture.rst)
- **数据模型**: [Data Model](guides/data_model.rst)
- **用户指南**:
  - [快速入门](getting_started.rst)
  - [高级用法](guides/advanced_usage.rst)
  - [配置指南](configuration.rst)
  - [部署指南](guides/deployment.rst)
  - [命令行工具](cli_reference.rst)
- **开发者指南**:
  - [贡献指南](CONTRIBUTING.md)
  - [引擎开发](guides/creating_an_engine.rst)

## 社区与贡献

- **GitHub 仓库**: https://github.com/your-org/trans-hub
- **报告问题**: https://github.com/your-org/trans-hub/issues
- **贡献代码**: 请参阅 [贡献指南](CONTRIBUTING.md)
- **讨论社区**: https://discord.gg/trans-hub

## 许可证

`Trans-Hub` 采用 MIT 许可证，详情请参阅项目根目录下的 LICENSE 文件.

## 目录结构

本项目的文档采用现代化的**扁平化目录结构**，没有独立的 `source` 目录。所有源文件（`.rst`）和配置文件（`conf.py`）都位于 `docs/` 根目录下。

```text
docs/
├── _build/             # 本地构建产物 (已在 .gitignore 中忽略)
├── _static/            # 静态文件 (CSS, 图片)
├── _templates/         # 自定义模板
├── api/                # API 参考文档源文件
├── guides/             # 指南和教程源文件
├── locale/             # 多语言翻译文件 (.po)
├── conf.py             # Sphinx 核心配置文件
├── index.rst           # 文档主页
├── Makefile            # 本地构建脚本 (Linux/macOS)
└── make.bat            # 本地构建脚本 (Windows)
```

## 本地构建

在进行任何修改后，强烈建议在本地构建以预览效果。

### 构建步骤

#### 1. 安装依赖

首先，请确保您已安装 `docs` 依赖组中声明的所有依赖项。

```bash
# 使用 poetry
poetry install --with docs

# 或者直接使用 pip
pip install -r requirements.txt
```

#### 2. 构建文档

在 `docs/` 目录下，运行以下命令：

```bash
# 在 Linux 或 macOS 上
make html

# 在 Windows 上
.\make.bat html
```

构建成功后，文档的入口文件位于 `docs/_build/html/index.html`。您可以在浏览器中打开它进行预览。

## 多语言工作流

我们的主语言是**中文 (`zh_CN`)**。所有 `.rst` 文件都应首先使用中文编写。其他语言的翻译通过 `sphinx-intl` 和 `.po` 文件进行管理。

### 翻译步骤

#### 1. 提取原文

当您修改了任何 `.rst` 文件后，需要更新翻译模板（`.pot` 文件）。

```bash
make gettext
```

此命令会扫描所有源文件，并将可翻译的文本提取到 `docs/_build/gettext/` 目录中。

#### 2. 更新翻译文件

接下来，更新特定语言的翻译文件（`.po` 文件）。我们已在 `Makefile` 中为此提供了便捷的快捷方式。

```bash
# 更新英语的 .po 文件
make update-po-en

# 更新日语的 .po 文件 (示例)
make update-po-ja
```

此命令会自动将新的或变更的文本条目添加到 `docs/locale/<lang>/LC_MESSAGES/` 目录下的 `.po` 文件中。您只需编辑这些文件，填写翻译即可。

#### 3. 本地预览特定语言的文档

要预览特定语言版本的网站，请使用以下命令：

```bash
# 预览英文版 (Linux/macOS)
make -e SPHINXOPTS="-D language=en" html

# 预览英文版 (Windows)
.\make.bat html -D language=en
```

## 自动化部署

本项目已与 **Read the Docs** 平台集成，配置见项目根目录下的 `.readthedocs.yaml` 文件。

-   任何推送到 `main` 分支的提交都会自动触发所有已定义语言的文档构建和部署。
-   提交 Pull Request 时，Read the Docs 会自动构建一个预览版本，方便审查文档变更。

因此，您**无需手动部署**。只需确保您的变更（包括更新的 `.po` 文件）已推送到代码仓库即可。