.. # docs/cli_reference.rst

======================
命令行工具 (CLI) 参考
======================

`Trans-Hub` 提供了一个强大的命令行接口（CLI），用于启动后台服务、提交翻译任务和管理数据库。

基本用法
--------

所有命令都通过 `trans-hub` 入口点执行。您可以通过 `--help` 选项查看帮助。

.. code-block:: shell

   trans-hub --help

.. note::
   在本文档中，我们将使用 ``trans-hub`` 作为命令的入口。根据您的安装方式，您可能需要使用 ``poetry run trans-hub``。

命令组
--------

### `worker`

用于管理后台 Worker 进程的命令组。

**`worker start`**

启动一个或多个后台工作进程，持续处理指定语言的待翻译任务。

.. code-block:: shell

   trans-hub worker start --lang <LANG_CODE> [OPTIONS]

- ``--lang, -l TEXT``: **[必需]** 要处理的目标语言代码。可多次指定。

### `request`

用于提交新翻译任务的命令组。

**`request new`**

提交一个新的翻译请求到队列中。

.. code-block:: shell

   trans-hub request new --id <BUSINESS_ID> --payload-json <JSON_STRING> --target <LANG_CODE> [OPTIONS]

**关键选项**:

- ``--id TEXT``: **[必需]** 关联内容的、全局唯一的业务 ID。
- ``--payload-json TEXT``: **[必需]** 要翻译的结构化内容，格式为 JSON 字符串。**必须**包含一个 `"text"` 键。 (例如: ``'{"text": "Hello", "note": "greeting"}'``)
- ``--target, -t TEXT``: **[必需]** 目标语言代码。此选项可多次指定。
- ``--source, -s TEXT``: (可选) 源语言代码。
- ``--context-json TEXT``: (可选) 与请求相关的上下文，格式为 JSON 字符串。
- ``--force, -f``: (可选) 强制重新翻译。

**示例**:

.. code-block:: shell
   :caption: 将带有业务 ID 的 "Hello" 翻译成德文和法文

   trans-hub request new --id "greeting.hello" --payload-json '{"text":"Hello"}' --target de --target fr

### `gc`

用于数据库垃圾回收的命令组。

**`gc run`**

执行数据库垃圾回收，清理过期的、无关联的旧数据。

- ``--days, -d INTEGER``: 保留最近多少天内的活跃任务。 (默认: 90)
- ``--yes, -y``: 自动确认，跳过交互式提示。

### `db`

用于数据库维护任务的命令组。

**`db migrate`**

对数据库应用所有必要的迁移脚本，使其达到最新的 Schema 版本。

.. code-block:: shell

   trans-hub db migrate