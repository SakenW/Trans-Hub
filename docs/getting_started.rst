.. # docs/getting_started.rst

==================
快速上手指南
==================

欢迎使用 `Trans-Hub`！本指南将带您在 5 分钟内完成从安装到第一次成功翻译的全过程。

预备知识
--------

- 您已安装并配置好 Python 3.10+ 环境。
- 您熟悉基本的命令行操作。

第一步：安装 Trans-Hub
========================

我们推荐使用 `Poetry` 来管理项目依赖。

.. code-block:: shell
   :caption: 使用 Poetry 安装 (推荐)

   # 安装核心库、CLI 工具和免费的 `translators` 引擎
   poetry add "trans-hub[cli,translators]"

或者，您也可以使用 `pip`：

.. code-block:: shell
   :caption: 使用 pip 安装

   pip install "trans-hub[cli,translators]"

安装完成后，您可以通过 `--version` 标志来验证 `trans-hub` CLI 是否可用。

.. code-block:: shell

   trans-hub --version

第二步：进行基本配置
--------------------

`Trans-Hub` 的配置可以通过 `.env` 文件轻松管理。在您的项目根目录下，创建一个名为 ``.env`` 的文件，并填入以下最基础的配置：

.. code-block:: shell
   :caption: .env

   # .env
   # 默认激活免费的 translators 引擎
   TH_ACTIVE_ENGINE="translators"

   # 指定一个本地数据库文件
   TH_DATABASE_URL="sqlite:///./transhub_quickstart.db"

   # 设置一个默认的源语言（对于 translators 引擎是可选的，但建议设置）
   TH_SOURCE_LANG="en"

   # 在入门阶段，将日志级别设为 DEBUG，方便观察内部流程
   TH_LOGGING__LEVEL="DEBUG"

.. note::
   `Trans-Hub` 会自动在当前目录或上级目录寻找 `.env` 文件。

第三步：初始化数据库
--------------------

这是**至关重要**的一步。在首次运行前，您必须初始化数据库，创建所有必要的表和索引。

.. code-block:: shell
   :caption: 运行数据库迁移命令

   trans-hub db migrate

您应该会看到一条类似“✅ 数据库迁移成功！”的消息。现在，一个名为 ``transhub_quickstart.db`` 的数据库文件应该已经出现在您的目录中。

第四步：提交您的第一个翻译请求
------------------------------

现在，让我们向系统提交一个翻译任务。我们将把 "Hello, world!" 翻译成中文和日文。

.. code-block:: shell
   :caption: 使用 request new 命令提交任务

   trans-hub request new --target zh-CN --target ja "Hello, world!"

执行后，您会看到一条确认消息。这个任务现在已经被登记在数据库中，状态为 `PENDING`。

第五步：启动 Worker 并观察结果
=================================

现在，我们需要启动一个后台工作进程（Worker）来处理我们刚刚提交的任务。

请打开一个新的终端窗口（保持当前窗口不变），并运行以下命令来启动一个专门处理中文和日文翻译的 Worker：

.. code-block:: shell
   :caption: 在新终端中启动 Worker

   trans-hub worker start --lang zh-CN --lang ja

启动后，您将看到 Worker 开始轮询数据库，发现并处理待办任务。由于我们将日志级别设为 `DEBUG`，您会看到详细的日志输出，包括翻译成功或失败的信息。

成功了！
--------

恭喜您！您已经成功地完成了 `Trans-Hub` 的一次完整工作流。您刚刚体验了 `Trans-Hub` 设计的核心：**通过 `request new` 命令将任务登记与耗时的翻译处理解耦，并由独立的 `worker start` 进程在后台完成实际工作。**

下一步
------

现在您已经掌握了基本操作，可以开始探索 `Trans-Hub` 的更多功能了：

- 查阅 :doc:`配置指南 <configuration>` 来了解所有可用的配置项。
- 学习 :doc:`命令行工具参考 <cli_reference>` 以掌握更多管理命令。
- 阅读 :doc:`高级用法指南 <guides/advanced_usage>` 来探索上下文翻译、并发控制和与 Web 框架集成等高级主题。
- 探索 :doc:`核心架构 <guides/architecture>` 以深入理解其内部工作原理。