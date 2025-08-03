.. # docs/cli_reference.rst

======================
命令行工具 (CLI) 参考
======================

`Trans-Hub` 提供了一个强大的命令行接口（CLI），用于启动后台服务、提交翻译任务和管理数据库。

基本用法
--------

所有命令都通过 `trans-hub` 入口点执行，并采用“命令组”结构。您可以通过 `--help` 选项查看所有可用的命令组。

.. code-block:: shell

   trans-hub --help

.. note::
   在本文档中，我们将使用 ``trans-hub`` 作为命令的入口。根据您的安装方式，您可能需要使用 ``poetry run trans-hub``。

命令组
--------

### `worker`

用于管理后台 Worker 进程的命令组。

**`worker start`**

启动一个或多个后台工作进程，持续处理指定语言的待翻译任务。这是 `Trans-Hub` 的核心服务命令。

.. code-block:: shell

   trans-hub worker start --lang <LANG_CODE> [OPTIONS]

**关键选项**:

- ``--lang, -l TEXT``: **[必需]** 要处理的目标语言代码。此选项可多次指定以同时处理多种语言。 (例如: ``--lang en --lang zh-CN``)

**示例**:

.. code-block:: shell
   :caption: 启动一个处理中文和日文翻译的 Worker

   trans-hub worker start --lang zh-CN --lang ja

### `request`

用于提交新翻译任务的命令组。

**`request new`**

提交一个新的翻译请求到队列中，供后台 Worker 处理。

.. code-block:: shell

   trans-hub request new [OPTIONS] <TEXT_TO_TRANSLATE>

**参数**:

- ``TEXT_TO_TRANSLATE``: **[必需]** 要翻译的原文，作为命令的最后一个参数。

**关键选项**:

- ``--target, -t TEXT``: **[必需]** 目标语言代码。此选项可多次指定。 (例如: ``--target en --target fr``)
- ``--source, -s TEXT``: (可选) 源语言代码。如果未提供，将使用全局配置中的值。
- ``--id TEXT``: (可选) 用于追踪的业务 ID。
- ``--force, -f``: (可选) 强制重新翻译，即使已有缓存或已完成的翻译。

**示例**:

.. code-block:: shell
   :caption: 将 "你好" 翻译成英文和法文

   trans-hub request new --target en --target fr "你好"

.. code-block:: shell
   :caption: 强制重新翻译一个带有业务 ID 的术语

   trans-hub request new --target ja --id "term.login" --force "登录"

### `gc`

用于数据库垃圾回收的命令组。

**`gc run`**

执行数据库垃圾回收，清理过期的、无关联的旧数据。

.. code-block:: shell

   trans-hub gc run [OPTIONS]

**关键选项**:

- ``--days, -d INTEGER``: 保留最近多少天内的活跃任务。 (默认: 90)
- ``--yes, -y``: (可选) 自动确认，跳过交互式提示直接执行删除。在脚本或 CI 环境中非常有用。

**示例**:

.. code-block:: shell
   :caption: 预览将要被清理的数据 (默认行为)

   trans-hub gc run --days 30
   # (程序会显示预演报告并请求用户确认)

.. code-block:: shell
   :caption: 在脚本中自动执行清理操作

   trans-hub gc run --days 30 --yes

### `db`

用于所有与数据库直接相关的维护任务的命令组。

**`db migrate`**

对数据库应用所有必要的迁移脚本，使其达到最新的 Schema 版本。这是初始化新数据库或升级 `Trans-Hub` 版本后的**必要步骤**。

.. code-block:: shell

   trans-hub db migrate

**示例**:

.. code-block:: shell
   :caption: 对默认数据库执行迁移

   trans-hub db migrate