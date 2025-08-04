.. # docs/getting_started.rst

==================
快速上手指南
==================

本指南将带您在 5 分钟内完成从安装到第一次成功翻译的全过程。

第一步：安装 Trans-Hub
========================

.. code-block:: shell

   pip install "trans-hub[cli,translators]"

安装完成后，验证 CLI 是否可用：

.. code-block:: shell

   trans-hub --version

第二步：进行基本配置
--------------------

在您的项目根目录下，创建一个名为 ``.env`` 的文件：

.. code-block:: shell
   :caption: .env

   # 激活免费的 translators 引擎
   TH_ACTIVE_ENGINE="translators"
   # 指定一个本地数据库文件
   TH_DATABASE_URL="sqlite:///./transhub_quickstart.db"
   # 设置默认源语言
   TH_SOURCE_LANG="en"

第三步：初始化数据库
--------------------

**至关重要的一步**。运行数据库迁移来创建所有表。

.. code-block:: shell

   trans-hub db migrate

第四步：提交您的第一个翻译请求
------------------------------

我们将把一个带有业务 ID ``greeting.hello`` 的文本 "Hello, world!" 翻译成中文和日文。

.. code-block:: shell
   :caption: 使用 request new 命令提交任务

   trans-hub request new --id "greeting.hello" --payload-json '{"text": "Hello, world!"}' --target zh-CN --target ja

第五步：启动 Worker 并观察结果
=================================

打开一个新的终端窗口，启动一个 Worker 来处理我们刚提交的任务：

.. code-block:: shell
   :caption: 在新终端中启动 Worker

   trans-hub worker start --lang zh-CN --lang ja

启动后，您将看到 Worker 开始处理任务并打印成功日志。

恭喜您！您已经成功地体验了 `Trans-Hub` 的核心工作流。

下一步
------

- 查阅 :doc:`配置指南 <configuration>`
- 学习 :doc:`命令行工具参考 <cli_reference>`
- 阅读 :doc:`高级用法指南 <guides/advanced_usage>`