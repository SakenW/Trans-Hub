# Guide 4: Deployment and Operations

Welcome to the deployment and operation guide for `Trans-Hub`. This guide aims to provide key best practices for developers and operations engineers who wish to run `Trans-Hub` stably in a **production environment**.

We will cover database management, deployment patterns for background tasks, high concurrency processing, and data lifecycle maintenance.

[Return to Document Index](../INDEX.md)

---

## **1. 核心部署理念：分离关注点**

在生产环境中，`Trans-Hub` 的工作流通常被分离为两个主要部分：

1.  **API 应用 (Producers)**: 负责接收用户请求并快速响应。它的主要职责是调用 `Coordinator.request()` 来**登记**翻译任务。
2.  **后台工作进程 (Worker)**: 一个或多个独立的、长期运行的进程。它的唯一职责是持续调用 `Coordinator.process_pending_translations()` 来**处理**积压的任务。

这种分离确保了即使用户的翻译请求量激增，API 应用也能保持低延迟，因为它只做最轻量级的数据库写入操作。繁重的、耗时的翻译任务则由后台的 Worker 异步处理。

---

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

# On application startup
def startup():
    DB_FILE = "/path/to/your/production.db

    print("Checking and applying database migrations...")
    apply_migrations(DB_FILE)
    print("The database is up to date.")

    # ... Subsequent application initialization logic ...

---

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
                    log.info(f"正在检查 'en' 的任务...")
                    processed_count = 0
                    async for result in coordinator.process_pending_translations(lang):
                        processed_count += 1
                    if processed_count > 0:
                        log.info(f"本轮处理了 {processed_count} 个 'en' 任务。")

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

### **3.2 运行 Worker**

你应该使用一个进程管理工具（如 `systemd`, `supervisor`）来确保你的 `worker.py` 脚本能够作为后台服务长期运行，并在意外崩溃时自动重启。

---

## **4. High Concurrent Writes and `database is locked` Error**

This is an advanced topic that requires special attention when performing large-scale concurrent writes using the SQLite backend.

### **Scene**

When you have an application that needs to **call `coordinator.request()` hundreds of times in a very short period of time and concurrently** (for example, a batch import script, or concurrently processing a large number of files like our `doc_translator` tool), you may encounter the `sqlite3.OperationalError: database is locked` error.

### **Reason**

- **Concurrency Storm**: Concurrent tools like `asyncio.gather` will start a large number of coroutines that need to write to the database simultaneously.
- **Write Lock**: The `PersistenceHandler` in `Trans-Hub` has an internal asynchronous write lock that serializes these concurrent write requests.
- **SQLite Timeout**: When a request waits for the write lock longer than SQLite's default timeout (usually 5 seconds), it will fail and throw a `database is locked` error.

This is not a bug of `Trans-Hub`, but rather a physical limitation of any high-concurrency application when using SQLite.

### **Solution: Use `asyncio.Semaphore` at the application layer**

The best solution is to perform **throttling** on concurrency at **your application layer**. `asyncio.Semaphore` is the perfect tool to achieve this.

Core idea: Create a `Semaphore` to limit how many tasks calling `coordinator.request()` are running **simultaneously**.

**Sample Code:**

```python
# a_batch_importer.py
import asyncio
from trans_hub import Coordinator

MAX_CONCURRENT_REQUESTS = 10 # Adjust according to your server performance and I/O

async def process_item(item: dict, coordinator: Coordinator, semaphore: asyncio.Semaphore):
    # Asynchronously acquire the semaphore before executing the operation
    async with semaphore:
        # In this code block, at most MAX_CONCURRENT_REQUESTS will be running simultaneously
        await coordinator.request(
            target_langs=["zh-CN"],
            text_content=item["text"],
            business_id=item["id"]
        )

async def main():
    # ... (initialize coordinator) ...
    semaphore = asyncio.Semaphore(MAX_CONCURRENT_REQUESTS)

    all_items = [...] # Assume there are 1000 items here

    tasks = [process_item(item, coordinator, semaphore) for item in all_items]
    await asyncio.gather(*tasks)

    I'm sorry, but it seems that the text you provided is incomplete or not visible. Please provide the full text you would like translated.

Through this model, you leverage the concurrent advantages of `asyncio` while gently treating your database, avoiding failures caused by timeouts.

---

## **5. 维护：垃圾回收 (GC)**

使用 `cron` 来定期（例如每天凌晨）执行这个脚本。

**`crontab` 条目示例 (每天凌晨 3:30 执行)**:

```cron
30 3 * * * /path/to/your/poetry/bin/poetry run python /path/to/your/project/run_gc.py >> /var/log/trans-hub-gc.log 2>&1
```

---

## **6. Production Environment Configuration List**

Before deployment, please check the following configuration points:

- [ ] **Log Format**: Ensure that `TransHubConfig` or environment variables set `logging.format` to `"json"`.
- [ ] **Database Path**: Ensure that `database_url` points to an absolute path with persistent storage and the correct permissions.
- [ ] **Environment Variables**: Ensure that all sensitive information (such as `TH_OPENAI_API_KEY`) is correctly configured in the production environment via environment variables or a `.env` file.
- [ ] **Background Worker**: Ensure that at least one `worker.py` process is continuously running in the background.
- [ ] **GC Scheduling**: Ensure that `cron` or other scheduled tasks are set up to run `run_gc.py` regularly.
- [ ] **Database Backup**: Establish a regular backup strategy for your database files (if using SQLite) or database server.
