# Guide 4: Deployment and Operations

Welcome to the deployment and operation guide for `Trans-Hub`. This guide aims to provide key best practices for developers and operations engineers who wish to run `Trans-Hub` stably in a **production environment**.

We will cover database management, deployment patterns for background tasks, and data lifecycle maintenance.

[Return to Document Index](../INDEX.md)

It seems there is no text provided for translation. Please provide the text you would like to have translated.

## **1. 核心部署理念：分离关注点**

在生产环境中，`Trans-Hub` 的工作流通常被分离为两个主要部分：

1.  **API 应用 (同步/Web)**: 负责接收用户请求并快速响应。它的主要职责是调用 `Coordinator.request()` 来**登记**翻译任务。
2.  **后台工作进程 (Worker)**: 一个或多个独立的、长期运行的进程。它的唯一职责是持续调用 `Coordinator.process_pending_translations()` 来**处理**积压的任务。

这种分离确保了即使用户的翻译请求量激增，API 应用也能保持低延迟，因为它只做最轻量级的数据库写入操作。繁重的、耗时的翻译任务（涉及网络 I/O）则由后台的 Worker 异步处理。

It seems there is no text provided for translation. Please provide the text you would like to have translated.

## **2. Database Management**

### **2.1 Database Selection**

- **SQLite**: For small to medium-sized applications, SQLite (the default configuration for `Trans-Hub`) is an excellent choice with zero management costs. Please ensure that the application server has **read and write permissions** for the database file (`.db`) and its directory.
- **PostgreSQL/MySQL**: For large-scale, high-concurrency applications, or scenarios that require multi-node deployment of Workers, we strongly recommend implementing a custom `PersistenceHandler` based on PostgreSQL (`asyncpg`) or MySQL.

### **2.2 Database Migration**

This is a critical step that must be performed every time a deployment or application startup occurs.

Trans-Hub uses independent SQL files to manage the evolution of the database schema. The `apply_migrations()` function checks the current schema version of the database and applies all new migration scripts in order.

Best Practice: Place the `apply_migrations()` call at the very beginning of your application startup logic, before initializing any `Coordinator` instances.

```python
# main_app.py (应用入口)
from trans_hub.db.schema_manager import apply_migrations
from trans_hub.config import TransHubConfig

# On application startup
def startup():
    DB_FILE = "/path/to/your/production.db

    print("Checking and applying database migrations...")
    apply_migrations(DB_FILE)
    print("The database is up to date.")

    # ... Subsequent application initialization logic ...

It seems there is no text provided for translation. Please provide the text you would like to have translated.

## **3. 部署后台工作进程 (Worker)**

后台 Worker 是 `Trans-Hub` 翻译能力的“心脏”。

### **3.1 Worker 脚本示例**

创建一个名为 `worker.py` 的脚本。它的逻辑非常简单：在一个无限循环中调用 `process_pending_translations`。

```python
# worker.py
import asyncio
import structlog
from trans_hub import Coordinator, DefaultPersistenceHandler, TransHubConfig
from trans_hub.logging_config import setup_logging

async def main():
    """一个长期运行的后台工作进程。"""
    setup_logging(log_level="INFO", log_format="json") # 生产环境使用 JSON 格式
    log = structlog.get_logger("worker")

    # 从 .env 或环境变量加载配置
    config = TransHubConfig()
    handler = DefaultPersistenceHandler(config.db_path)
    coordinator = Coordinator(config, handler)

    try:
        await coordinator.initialize()
        log.info("后台 Worker 启动，开始监听待处理任务...")

        while True:
            try:
                # 在这里定义你想处理的语言列表
                target_languages = ["zh-CN", "fr", "de", "ja"]

                for lang in target_languages:
                    log.info(f"正在检查 'en' 的任务...")
                    processed_count = 0
                    async for result in coordinator.process_pending_translations(lang):
                        processed_count += 1
                        log.debug("任务已处理", result=result)
                    if processed_count > 0:
                        log.info(f"本轮处理了 {processed_count} 个 'en' 任务。")

                # 所有语言都检查完毕后，等待一段时间再开始下一轮
                log.info("所有语言检查完毕，Worker 将在 60 秒后再次轮询。")
                await asyncio.sleep(60)

            except Exception:
                log.error("Worker 循环中发生意外错误，将在 60 秒后重试。", exc_info=True)
                await asyncio.sleep(60)
    finally:
        if "coordinator" in locals() and coordinator.initialized:
            await coordinator.close()
            log.info("后台 Worker 已关闭。")

if __name__ == "__main__":
    asyncio.run(main())

### **3.2 运行 Worker**

你应该使用一个进程管理工具（如 `systemd`, `supervisor`, 或 `pm2`）来确保你的 `worker.py` 脚本能够作为后台服务长期运行，并在意外崩溃时自动重启。

**使用 `systemd` 的服务单元文件示例 (`/etc/systemd/system/trans-hub-worker.service`)**:

```ini
[Unit]
Description=Trans-Hub Background Worker
After=network.target

[Service]
User=your_app_user
Group=your_app_group
WorkingDirectory=/path/to/your/project
# 确保 poetry 在 PATH 中，或者使用绝对路径
ExecStart=/path/to/your/poetry/bin/poetry run python worker.py
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

It seems there is no text provided for translation. Please provide the text you would like to have translated.

## **4. Maintenance: Garbage Collection (GC)**

Regularly running garbage collection is crucial for controlling database size and cleaning up useless data.

### **4.1 GC Script Example**

Create a standalone maintenance script named `run_gc.py`.

```python
# run_gc.py
import asyncio
import structlog
from trans_hub import Coordinator, DefaultPersistenceHandler, TransHubConfig
from trans_hub.logging_config import setup_logging

async def main():
    setup_logging(log_level="INFO", log_format="console")
    log = structlog.get_logger("gc_script")

    config = TransHubConfig() # Load configuration from .env
    handler = DefaultPersistenceHandler(config.db_path)
    coordinator = Coordinator(config, handler)

    try:
        await coordinator.initialize()
        log.info("Starting garbage collection...", retention_days=config.gc_retention_days)

        # GC is an IO-intensive operation and may take some time
        report = await coordinator.run_garbage_collection()

        log.info("✅ Garbage collection completed.", report=report)
    finally:
        if "coordinator" in locals() and coordinator.initialized:
            await coordinator.close()

if __name__ == "__main__":
    asyncio.run(main())

### **4.2 Scheduling GC Tasks**

Use `cron` to execute this script regularly (for example, every day at midnight).

**`crontab` entry example (executes daily at 3:30 AM):**

```cron
30 3 * * * /path/to/your/poetry/bin/poetry run python /path/to/your/project/run_gc.py >> /var/log/trans-hub-gc.log 2>&1
```

It seems there is no text provided for translation. Please provide the text you would like to have translated.

## **5. Production Environment Configuration List**

Before deployment, please check the following configuration points:

- [ ] **Log Format**: Ensure that `TransHubConfig` or environment variables set `logging.format` to `"json"`.
- [ ] **Database Path**: Ensure that `database_url` points to an absolute path with persistent storage and the correct permissions.
- [ ] **Environment Variables**: Ensure that all sensitive information (such as `TH_OPENAI_API_KEY`) is correctly configured in the production environment via environment variables or a `.env` file.
- [ ] **Background Worker**: Ensure that at least one `worker.py` process is continuously running in the background.
- [ ] **GC Scheduling**: Ensure that `cron` or other scheduled tasks are set up to run `run_gc.py` regularly.
- [ ] **Database Backup**: Establish a regular backup strategy for your database files (if using SQLite) or database server.
