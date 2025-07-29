# Guide 4: Deployment and Operations

Welcome to the deployment and operation guide for `Trans-Hub`. This guide aims to provide key best practices for developers and operations engineers who wish to run `Trans-Hub` stably in a **production environment**.

We will cover database management, deployment patterns for background tasks, high concurrency processing, and data lifecycle maintenance.

[Return to Document Index](../INDEX.md)

## **1. Core Deployment Philosophy: Separation of Concerns**

In a production environment, the workflow of `Trans-Hub` is usually divided into two main parts:

1.  **API Application (Producers)**: Responsible for receiving user requests and responding quickly. Its main duty is to call `Coordinator.request()` to **register** translation tasks.  
2.  **Background Worker (Worker)**: One or more independent, long-running processes. Its sole responsibility is to continuously call `Coordinator.process_pending_translations()` to **process** the backlog of tasks.

This separation ensures that even if there is a surge in user translation requests, the API application can maintain low latency, as it only performs the lightest database write operations. The heavy and time-consuming translation tasks are handled asynchronously by backend workers.

## **2. Database Management**

### **2.1 Database Selection**

- **SQLite**: For small to medium-sized applications, SQLite (the default configuration for `Trans-Hub`) is an excellent choice with zero management costs. Please ensure that the application server has **read and write permissions** for the database file (`.db`) and its directory.
- **PostgreSQL/MySQL**: For large-scale, high-concurrency applications, or scenarios that require multi-node deployment of Workers, we strongly recommend implementing a custom `PersistenceHandler` based on PostgreSQL (`asyncpg`) or MySQL.

### **2.2 Database Migration**

This is a critical step that must be performed every time a deployment or application startup occurs.

The `apply_migrations()` function checks the current schema version of the database and applies all new migration scripts in order.

Best Practice: Place the `apply_migrations()` call at the very beginning of your application startup logic, before initializing any `Coordinator` instances.

```python
# main_app.py (应用入口)
from trans_hub.db.schema_manager import apply_migrations

# 在应用启动时
def startup():
    DB_FILE = "/path/to/your/production.db"

    print("正在检查并应用数据库迁移...")
    apply_migrations(DB_FILE)
    print("数据库已是最新版本。")

    # ... 后续的应用初始化逻辑 ...
```

## **3. Deploying Background Worker Processes**

The backend Worker is the "heart" of the `Trans-Hub` translation capability.

### **3.1 Worker Script Example**

Create a script named `worker.py`. Its logic is very simple: call `process_pending_translations` in an infinite loop.

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

    config = TransHubConfig()
    handler = DefaultPersistenceHandler(config.db_path)
    coordinator = Coordinator(config, handler)

    try:
        await coordinator.initialize()
        log.info("后台 Worker 启动，开始监听待处理任务...")

        while True:
            try:
                target_languages = ["zh-CN", "fr", "de", "ja"]
                for lang in target_languages:
                    log.info(f"正在检查 '{lang}' 的任务...")
                    processed_count = 0
                    async for result in coordinator.process_pending_translations(lang):
                        processed_count += 1
                    if processed_count > 0:
                        log.info(f"本轮处理了 {processed_count} 个 '{lang}' 任务。")

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
```

### **3.2 Run Worker**

You should use a process management tool (such as `systemd` or `supervisor`) to ensure that your `worker.py` script can run as a background service for a long time and automatically restart in case of an unexpected crash.

## **4. High Concurrency Writes and `database is locked` Error**

This is an advanced topic that requires special attention when performing large-scale concurrent writes using the SQLite backend.

### **Scene**

When you have an application that needs to **call `coordinator.request()` hundreds of times in a very short time and concurrently** (for example, a batch import script, or concurrently processing a large number of files like our `doc_translator` tool), you may encounter the `sqlite3.OperationalError: database is locked` error.

### **Reason**

- **Concurrency Storm**: Concurrent tools like `asyncio.gather` will start a large number of coroutines that need to write to the database simultaneously.
- **Write Lock**: The `PersistenceHandler` in `Trans-Hub` has an internal asynchronous write lock that serializes these concurrent write requests.
- **SQLite Timeout**: When a request waits for the write lock longer than SQLite's default timeout (usually 5 seconds), it will fail and throw a `database is locked` error.

This is not a bug of `Trans-Hub`, but rather a physical limitation of any high-concurrency application when using SQLite.

### **Solution: Use `asyncio.Semaphore` at the application layer**

The best solution is to throttle concurrency at **your application layer**. `asyncio.Semaphore` is the perfect tool to achieve this.

**Core Idea**: Create a `Semaphore` to limit **how many** tasks calling `coordinator.request()` are running **simultaneously**.

**Sample Code:**

```python
# a_batch_importer.py
import asyncio
from trans_hub import Coordinator

MAX_CONCURRENT_REQUESTS = 10 # 根据你的服务器性能和 I/O 调整

async def process_item(item: dict, coordinator: Coordinator, semaphore: asyncio.Semaphore):
    # 在执行操作前，先异步地获取信号量
    async with semaphore:
        # 这里的代码块，同时最多只会有 MAX_CONCURRENT_REQUESTS 个在运行
        await coordinator.request(
            target_langs=["zh-CN"],
            text_content=item["text"],
            business_id=item["id"]
        )

async def main():
    # ... (初始化 coordinator) ...
    semaphore = asyncio.Semaphore(MAX_CONCURRENT_REQUESTS)

    all_items = [...] # 假设这里有 1000 个项目

    tasks = [process_item(item, coordinator, semaphore) for item in all_items]
    await asyncio.gather(*tasks)

    # ...
```

Through this model, you leverage the concurrent advantages of `asyncio` while gently treating your database, avoiding failures caused by timeouts.

## **5. Maintenance: Garbage Collection (GC)**

Use `cron` to execute this script regularly (for example, every day at midnight).

**`crontab` entry example (executes daily at 3:30 AM):**

```cron
30 3 * * * /path/to/your/poetry/bin/poetry run python /path/to/your/project/run_gc.py >> /var/log/trans-hub-gc.log 2>&1
```

## **6. Production Environment Configuration List**

Before deployment, please check the following configuration points:

- [ ] **Log Format**: Ensure that `TransHubConfig` or environment variables set `logging.format` to `"json"`.
- [ ] **Database Path**: Ensure that `database_url` points to an absolute path with persistent storage and the correct permissions.
- [ ] **Environment Variables**: Ensure that all sensitive information (such as `TH_OPENAI_API_KEY`) is correctly configured in the production environment through environment variables or a `.env` file.
- [ ] **Background Worker**: Ensure that at least one `worker.py` process is continuously running in the background.
- [ ] **GC Scheduling**: Ensure that `cron` or other scheduled tasks are set up to run `run_gc.py` regularly.
- [ ] **Database Backup**: Establish a regular backup strategy for your database files (if using SQLite) or database server.
