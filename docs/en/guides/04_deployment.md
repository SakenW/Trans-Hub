# Guide 4: Deployment and Operations

Welcome to the deployment and operation guide for `Trans-Hub`. This guide aims to provide key best practices for developers and operations engineers who wish to run `Trans-Hub` stably in a **production environment**.

We will cover database management, deployment patterns for background tasks, and data lifecycle maintenance.

[Return to Document Index](../INDEX.md)

It seems there is no text provided for translation. Please provide the text you would like to have translated.

## **1. Core Deployment Philosophy: Separation of Concerns**

In a production environment, the workflow of `Trans-Hub` is typically divided into two main parts:

1.  **API Application (Synchronous/Web)**: Responsible for receiving user requests and responding quickly. Its main duty is to call `Coordinator.request()` to **register** translation tasks.  
2.  **Background Worker (Worker)**: One or more independent, long-running processes. Its sole responsibility is to continuously call `Coordinator.process_pending_translations()` to **process** backlog tasks.

This separation ensures that even if there is a surge in user translation requests, the API application can maintain low latency, as it only performs the lightest database write operations. Heavy and time-consuming translation tasks (involving network I/O) are handled asynchronously by backend workers.

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
    """A long-running background worker process."""
    setup_logging(log_level="INFO", log_format="json") # Use JSON format in production environment
    log = structlog.get_logger("worker")

    # Load configuration from .env or environment variables
config = TransHubConfig()
handler = DefaultPersistenceHandler(config.db_path)
coordinator = Coordinator(config, handler)

    try:
        await coordinator.initialize()
        log.info("Background Worker started, beginning to listen for pending tasks...")

        while True:
            try:
                # Define the list of languages you want to process here
                target_languages = ["zh-CN", "fr", "de", "ja"]

                for lang in target_languages:
                    log.info(f"Checking tasks for '{lang}'...")
                    processed_count = 0
                    async for result in coordinator.process_pending_translations(lang):
                        processed_count += 1
                        log.debug("Task processed", result=result)
                    if processed_count > 0:
                        log.info(f"Processed {processed_count} '{lang}' tasks this round.")

                # After all languages have been checked, wait for a while before starting the next round
                log.info("All language checks are complete, the Worker will poll again in 60 seconds.")
                await asyncio.sleep(60)

            except Exception:
                log.error("An unexpected error occurred in the Worker loop, will retry in 60 seconds.", exc_info=True)
                await asyncio.sleep(60)
    finally:
        if "coordinator" in locals() and coordinator.initialized:
            await coordinator.close()
            log.info("Background Worker has been closed.")

if __name__ == "__main__":
    asyncio.run(main())

### **3.2 Run Worker**

You should use a process management tool (such as `systemd`, `supervisor`, or `pm2`) to ensure that your `worker.py` script can run as a background service for a long time and automatically restart in case of an unexpected crash.

Example of a service unit file using `systemd` (`/etc/systemd/system/trans-hub-worker.service`):

```ini
[Unit]
Description=Trans-Hub Background Worker
After=network.target

[Service]  
User=your_app_user  
Group=your_app_group  
WorkingDirectory=/path/to/your/project  
# Ensure poetry is in PATH, or use absolute path  
ExecStart=/path/to/your/poetry/bin/poetry run python worker.py  
Restart=always  
RestartSec=10

[Install]  
WantedBy=multi-user.target

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
