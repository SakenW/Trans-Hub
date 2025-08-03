.. # docs/guides/deployment.rst

==================
部署指南
==================

本指南提供了将 `Trans-Hub` 部署到生产环境的最佳实践和步骤。

系统要求
--------

- **Python**: 3.9 或更高版本。
- **数据库**: **SQLite** 是当前内置的唯一支持。为了在生产环境中获得更好的并发性能，请确保您的文件系统和操作系统支持 SQLite 的 WAL (Write-Ahead Logging) 模式。我们的迁移脚本会自动尝试启用它。
- **环境**: 推荐在隔离的虚拟环境（如 `venv` 或 `Poetry` 管理的环境）中运行。

部署步骤
--------

### 第一步：安装

在您的生产服务器上，我们推荐从 PyPI 安装，并包含您计划使用的引擎以及 CLI 工具所需的附加依赖。

.. code-block:: shell

   # 示例：安装核心库、CLI 工具以及 OpenAI 引擎
   pip install "trans-hub[cli,openai]"

### 第二步：配置

在生产环境中，强烈推荐使用 ``.env`` 文件或环境变量来管理配置，特别是敏感的 API 密钥。

在您的部署目录下，创建一个 ``.env`` 文件。

.. code-block:: shell
   :caption: /path/to/your/deployment/.env

   # -- 生产环境推荐配置 --

   # 1. 核心配置
   TH_ACTIVE_ENGINE="openai"
   TH_DATABASE_URL="sqlite:////var/data/trans_hub_prod.db" # 使用绝对路径
   TH_SOURCE_LANG="en"

   # 2. 日志配置
   TH_LOGGING__LEVEL="INFO"      # 生产环境使用 INFO 级别
   TH_LOGGING__FORMAT="json"     # 使用 JSON 格式以便机器解析

   # 3. 引擎配置 (以 OpenAI 为例)
   TH_ENGINE_CONFIGS__OPENAI__OPENAI_API_KEY="sk-xxxxxxxxxxxxxxxx"
   TH_ENGINE_CONFIGS__OPENAI__RPM=3000 # 根据您的 API 限制设置

   # 4. 策略配置
   TH_RETRY_POLICY__MAX_ATTEMPTS=4  # 增加重试次数
   TH_CACHE_CONFIG__TTL=86400       # 缓存一天

.. warning::
   请确保 `.env` 文件和数据库文件（例如 ``/var/data/trans_hub_prod.db``）的目录权限设置正确，运行 Worker 的用户有权读取 `.env` 文件和读写数据库文件。

### 第三步：初始化数据库

在首次启动 Worker 之前，必须运行数据库迁移来初始化数据库 Schema。

.. code-block:: shell

   # 在您的部署目录下运行
   trans-hub db migrate

### 第四步：使用 systemd 运行 Worker 进程

为了保证 Worker 进程能够在后台持续运行并在失败时自动重启，强烈推荐使用进程管理工具，如 `systemd` 或 `supervisor`。

以下是一个 `systemd` 服务的示例配置文件。请在 ``/etc/systemd/system/trans-hub-worker.service`` 创建此文件。

.. code-block:: ini
   :caption: /etc/systemd/system/trans-hub-worker.service

   [Unit]
   Description=Trans-Hub Background Worker
   After=network.target

   [Service]
   # 替换为实际运行服务的用户和组
   User=myapp_user
   Group=myapp_group

   # 替换为您的部署目录
   WorkingDirectory=/opt/my_app/trans-hub

   # 关键：确保使用您安装了 trans-hub 的虚拟环境中的可执行文件
   # 如果使用 Poetry，路径可能类似 /home/myapp_user/.cache/pypoetry/virtualenvs/.../bin/trans-hub
   # 如果使用 venv，路径可能类似 /opt/my_app/trans-hub/.venv/bin/trans-hub
   ExecStart=/path/to/your/virtualenv/bin/trans-hub run-worker --lang en --lang zh-CN

   # 从部署目录加载 .env 文件
   EnvironmentFile=/opt/my_app/trans-hub/.env

   Restart=always
   RestartSec=10s

   [Install]
   WantedBy=multi-user.target

配置完成后，启动并启用该服务：

.. code-block:: shell

   systemctl daemon-reload
   systemctl start trans-hub-worker
   systemctl enable trans-hub-worker
   systemctl status trans-hub-worker

您可以通过 `journalctl` 查看 Worker 的实时日志：

.. code-block:: shell

   journalctl -u trans-hub-worker -f

高可用与扩展
------------

- **多 Worker 部署**: 您可以为不同的语言启动不同的 Worker 服务。只需复制 ``trans-hub-worker.service`` 文件（例如，命名为 `trans-hub-worker-fr.service`），并修改 ``ExecStart`` 中的 ``--lang`` 参数即可。
- **数据库扩展**: 虽然目前仅支持 SQLite，但 `PersistenceHandler` 的设计允许您通过实现该接口来接入 PostgreSQL 等更强大的数据库，以支持更高的并发写入。

安全最佳实践
------------

- **使用环境变量**: 切勿将 API 密钥等敏感信息硬编码在代码中。始终使用 `.env` 文件或环境变量。
- **文件权限**: 限制对 `.env` 文件和数据库文件的访问权限。
- **最小权限原则**: 运行 Worker 的系统用户应被授予最小必要的权限。
- **定期备份**: 定期备份您的 SQLite 数据库文件。

升级 `Trans-Hub`
==================

1.  **停止服务**: `sudo systemctl stop trans-hub-worker`
2.  **备份数据库**: `cp /var/data/trans_hub_prod.db /var/data/trans_hub_prod.db.bak`
3.  **升级包**: `pip install --upgrade "trans-hub[cli,openai]"`
4.  **应用数据库迁移**: `trans-hub db migrate`
5.  **重启服务**: `sudo systemctl start trans-hub-worker`