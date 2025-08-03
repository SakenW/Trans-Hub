.. # docs/cli_reference.rst

======================
命令行工具 (CLI) 参考
======================

`Trans-Hub` 提供了一个强大的命令行接口（CLI），用于启动后台服务、提交翻译任务和管理数据库。

基本用法
--------

所有命令都通过 `trans-hub` 入口点执行。您可以通过 `--help` 选项查看所有可用的命令和子命令。

.. code-block:: shell
   

   trans-hub --help

.. note::
   在本文档中，我们将使用 ``trans-hub`` 作为命令的入口。根据您的安装方式，您可能需要使用 ``poetry run trans-hub``。

核心命令
--------

### `run-worker`

启动一个或多个后台工作进程，持续处理指定语言的待翻译任务。这是 `Trans-Hub` 的核心服务命令。

.. code-block:: shell


   trans-hub run-worker --lang <LANG_CODE> [OPTIONS]

**关键选项**:

- ``--lang, -l TEXT``: **[必需]** 要处理的目标语言代码。此选项可多次指定以同时处理多种语言。 (例如: ``--lang en --lang zh-CN``)
- ``--batch-size, -b INTEGER``: 每个批次处理的任务数量。 (默认: 50)
- ``--interval, -i INTEGER``: 当任务队列为空时，轮询数据库的间隔时间（秒）。 (默认: 5)

**示例**:

.. code-block:: shell
   :caption: 启动一个处理中文和日文翻译的 Worker


   trans-hub run-worker --lang zh-CN --lang ja

.. code-block:: shell
   :caption: 启动一个高吞吐量的英文 Worker

   trans-hub run-worker --lang en --batch-size 100 --interval 2

### `request`

提交一个新的翻译请求到队列中，供后台 Worker 处理。

.. code-block:: shell


   trans-hub request [OPTIONS] <TEXT_TO_TRANSLATE>

**参数**:

- ``TEXT_TO_TRANSLATE``: **[必需]** 要翻译的原文，作为命令的最后一个参数。

**关键选项**:

- ``--target, -t TEXT``: **[必需]** 目标语言代码。此选项可多次指定以请求多种语言的翻译。 (例如: ``--target en --target fr``)
- ``--source, -s TEXT``: (可选) 源语言代码。如果未提供，将使用全局配置中的值。
- ``--id TEXT``: (可选) 用于追踪的业务 ID。
- ``--force``: (可选) 强制重新翻译，即使已有缓存或已完成的翻译。

**示例**:

.. code-block:: shell
   :caption: 将 "你好" 翻译成英文和法文

   trans-hub request --target en --target fr "你好"

.. code-block:: shell
   :caption: 强制重新翻译一个带有业务 ID 的术语

   trans-hub request --target ja --id "term.login" --force "ログイン"

### `gc`

执行数据库垃圾回收，清理过期的、无关联的旧数据。

.. code-block:: shell

   trans-hub gc [OPTIONS]

**关键选项**:

- ``--days, -d INTEGER``: 保留最近多少天内的活跃任务。 (默认: 90)
- ``--dry-run``: (可选) 只显示将被删除的条目数量，不实际执行删除操作。这是一个进行破坏性操作前非常有用的安全检查。

**示例**:

.. code-block:: shell
   :caption: 预览将要被清理的数据

   trans-hub gc --dry-run --days 30

.. code-block:: shell
   :caption: 实际执行清理操作

   trans-hub gc --days 30
   # (程序会请求用户确认)

数据库管理 (`db`)
-----------------

这是一个子命令组，用于所有与数据库直接相关的维护任务。

### `db migrate`

对数据库应用所有必要的迁移脚本，使其达到最新的 Schema 版本。这是初始化新数据库或升级 `Trans-Hub` 版本后的**必要步骤**。

.. code-block:: shell

   trans-hub db migrate [OPTIONS]

**关键选项**:

- ``--db-url TEXT``: (可选) 覆盖配置中定义的数据库 URL。这在临时操作不同数据库时非常有用。

**示例**:

.. code-block:: shell
   :caption: 对默认数据库执行迁移

   trans-hub db migrate

.. code-block:: shell
   :caption: 对一个指定的数据库文件执行迁移

   trans-hub db migrate --db-url "sqlite:///./backup.db"