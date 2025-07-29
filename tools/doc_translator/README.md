# 文档翻译工具 (`doc_translator`) 说明文档

## 1. 概述

`doc_translator` 是一个命令行工具，旨在自动化多语言 Markdown 文档的翻译和发布流程。它与 `Trans-Hub` 翻译引擎深度集成，能够实现从源语言文档到多语言版本发布的端到端自动化。

核心功能包括：

*   **智能扫描**: 自动扫描源语言目录，发现所有待翻译的 Markdown 文件。
*   **结构保持**: 使用 `markdown-it-py` 精确解析 Markdown，确保在翻译过程中完整保留标题、列表、代码块、链接等所有结构。
*   **增量翻译**: 利用 `Trans-Hub` 的持久化和缓存能力，只对新增或变更的内容进行翻译，极大提高效率。
*   **动态链接**: 支持在 Markdown 中使用 `{lang}` 占位符，自动生成指向对应语言版本的动态链接。
*   **双语发布**: 可将指定文件（如 `README.md`）发布到项目根目录，并生成一个用户体验极佳的、可点击切换的页面级双语版本。
*   **职责分离**: 工具的功能被清晰地拆分为 `translate` (翻译)、`publish` (发布) 和 `sync` (同步) 三个独立的命令，提升了使用的灵活性和效率。

## 2. 目录结构约定

本工具的正常运行依赖于一个约定的目录结构：

```
PROJECT_ROOT/
└── docs/
    ├── en/
    │   ├── guides/
    │   │   └── 01_quickstart.md
    │   └── root_files/
    │       └── README.md
    └── zh/
        ├── guides/
        │   └── 01_quickstart.md
        └── root_files/
            └── README.md
```

*   **`docs/`**: 所有文档的根目录。
*   **`docs/<lang>/`**: 每个子目录代表一种语言，使用 BCP 47 语言代码（如 `en`, `zh`）命名。这是存放最终翻译结果的地方。
*   **`docs/<lang>/root_files/`**: 这是一个特殊目录。存放在此目录下的文件被视为“根文件”，它们在执行 `publish` 或 `sync` 命令时会被特殊处理。

## 3. 命令参考

### `translate`

**用途**: **【仅翻译】**。执行完整的翻译流程，将结果渲染到 `docs/<lang>/...` 目录。**此命令不涉及项目根目录的文件操作。**

**命令格式**:
```bash
poetry run python tools/doc_translator/main_cli.py translate [OPTIONS]
```

**选项**:
*   `--source, -s TEXT`: 源语言代码。 [默认: `zh`]
*   `--target, -t TEXT`: 一个或多个目标语言代码。可多次使用。 [默认: `en`]
*   `--force, -f`: 强制重新翻译所有内容，忽略缓存。
*   `--help`: 显示帮助信息。

---

### `publish`

**用途**: **【仅发布双语版本】**。读取 `docs/` 目录下已有的翻译文件，将“根文件”（如 `README.md`）以一个可点击切换的**页面级双语版本**发布到项目根目录。这是一个快速的本地操作，不涉及翻译。

**命令格式**:
```bash
poetry run python tools/doc_translator/main_cli.py publish [OPTIONS]
```

**选项**:
*   `--default, -d TEXT`: 项目的默认语言。此参数用于定位发布的源文件（例如 `docs/en/root_files/`）。 [默认: `en`]
*   `--help`: 显示帮助信息。

---

### `sync`

**用途**: **【一键同步】**。执行完整的“翻译 + 发布”流程，一步到位。这是最常用的命令。

**命令格式**:
```bash
poetry run python tools/doc_translator/main_cli.py sync [OPTIONS]
```

**工作流程**:
1.  自动执行 `translate` 命令的所有步骤。
2.  紧接着，自动执行 `publish` 命令的所有步骤。

**选项**: (此命令包含了 `translate` 的所有选项)
*   `--source, -s TEXT`: 源语言代码。 [默认: `zh`]
*   `--target, -t TEXT`: 一个或多个目标语言代码。 [默认: `en`]
*   `--default, -d TEXT`: 项目的默认语言。 [默认: `en`]
*   `--force, -f`: 强制重新翻译所有内容。
*   `--help`: 显示帮助信息。

## 4. 常见用例

*   **首次/日常完整同步项目**:
    ```bash
    # 一条命令完成所有工作
    poetry run python tools/doc_translator/main_cli.py sync
    ```

*   **只更新了非根目录的文件内容** (例如 `docs/zh/guides/a.md`):
    ```bash
    # 只需要重新运行翻译命令即可，无需发布
    poetry run python tools/doc_translator/main_cli.py translate
    ```

*   **文档内容未变，只想调整双语 `README.md` 的显示格式**:
    *   首先修改 `renderer.py` 中的 `_render_bilingual_page_collapsible` 方法。
    *   然后只运行发布命令，无需重新翻译。
    ```bash
    poetry run python tools/doc_translator/main_cli.py publish
    ```
```