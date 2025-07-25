# 指南 4：部署与运维

欢迎来到 `Trans-Hub` 的部署与运维指南。本指南旨在为希望在**生产环境**中稳定运行 `Trans-Hub` 的开发者和运维工程师提供关键的最佳实践。

我们将涵盖数据库管理、后台任务的部署模式以及数据生命周期维护。

[返回文档索引](../INDEX.md)

---

## **1. 核心部署理念：分离关注点**

在生产环境中，`Trans-Hub` 的工作流通常被分离为两个主要部分：

1.  **API 应用 (同步/Web)**: 负责接收用户请求并快速响应。它的主要职责是调用 `Coordinator.request()` 来**登记**翻译任务。
2.  **后台工作进程 (Worker)**: 一个或多个独立的、长期运行的进程。它的唯一职责是持续调用 `Coordinator.process_pending_translations()` 来**处理**积压的任务。

这种分离确保了即使用户的翻译请求量激增，API 应用也能保持低延迟，因为它只做最轻量级的数据库写入操作。繁重的、耗时的翻译任务（涉及网络 I/O）则由后台的 Worker 异步处理。

---

## **2. 数据库管理**

### **2.1 数据库选择**

- **SQLite**: 对于中小型应用，SQLite（`Trans-Hub` 的默认配置）是一个非常出色、零管理成本的选择。请确保应用服务器对数据库文件 (`.db`) 及其所在目录有**读写权限**。
- **PostgreSQL/MySQL**: 对于大规模、高并发的应用，或者需要多节点部署 Worker 的场景，我们强烈建议您实现一个基于 PostgreSQL (`asyncpg`) 或 MySQL 的自定义 `PersistenceHandler`。

### **2.2 数据库迁移**

**这是每次部署或应用启动时都必须执行的关键步骤。**

`Trans-Hub` 使用独立的 SQL 文件来管理数据库 schema 的演进。`apply_migrations()` 函数会检查数据库当前的 schema 版本，并按顺序应用所有新的迁移脚本。

**最佳实践**: 将 `apply_migrations()` 调用放在您的应用启动逻辑的最前端，在初始化任何 `Coordinator` 实例之前。

```python
# main_app.py (应用入口)
from trans_hub.db.schema_manager import apply_migrations
from trans_hub.config import TransHubConfig

# 在应用启动时
def startup():
    DB_FILE = "/path/to/your/production.db"

    print("正在检查并应用数据库迁移...")
    apply_migrations(DB_FILE)
    print("数据库已是最新版本。")

    # ... 后续的应用初始化逻辑 ...
```

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
                    log.info(f"正在检查 '{lang}' 的任务...")
                    processed_count = 0
                    async for result in coordinator.process_pending_translations(lang):
                        processed_count += 1
                        log.debug("任务已处理", result=result)
                    if processed_count > 0:
                        log.info(f"本轮处理了 {processed_count} 个 '{lang}' 任务。")

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
```

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

---

## **4. 维护：垃圾回收 (GC)**

定期运行垃圾回收对于控制数据库大小和清理无用数据至关重要。

### **4.1 GC 脚本示例**

创建一个名为 `run_gc.py` 的独立维护脚本。

```python
# run_gc.py
import asyncio
import structlog
from trans_hub import Coordinator, DefaultPersistenceHandler, TransHubConfig
from trans_hub.logging_config import setup_logging

async def main():
    setup_logging(log_level="INFO", log_format="console")
    log = structlog.get_logger("gc_script")

    config = TransHubConfig() # 从 .env 加载配置
    handler = DefaultPersistenceHandler(config.db_path)
    coordinator = Coordinator(config, handler)

    try:
        await coordinator.initialize()
        log.info("开始执行垃圾回收...", retention_days=config.gc_retention_days)

        # GC 是一个 IO 密集型操作，可能需要一些时间
        report = await coordinator.run_garbage_collection()

        log.info("✅ 垃圾回收执行完毕。", report=report)
    finally:
        if "coordinator" in locals() and coordinator.initialized:
            await coordinator.close()

if __name__ == "__main__":
    asyncio.run(main())
```

### **4.2 调度 GC 任务**

使用 `cron` 来定期（例如每天凌晨）执行这个脚本。

**`crontab` 条目示例 (每天凌晨 3:30 执行)**:

```cron
30 3 * * * /path/to/your/poetry/bin/poetry run python /path/to/your/project/run_gc.py >> /var/log/trans-hub-gc.log 2>&1
```

---

## **5. 生产环境配置清单**

在部署前，请检查以下配置点：

- [ ] **日志格式**: 确保 `TransHubConfig` 或环境变量将 `logging.format` 设置为 `"json"`。
- [ ] **数据库路径**: 确保 `database_url` 指向一个具有持久化存储和正确权限的绝对路径。
- [ ] **环境变量**: 确保所有敏感信息（如 `TH_OPENAI_API_KEY`）都已通过环境变量或 `.env` 文件在生产环境中正确配置。
- [ ] **后台 Worker**: 确保至少有一个 `worker.py` 进程在后台持续运行。
- [ ] **GC 调度**: 确保已设置 `cron` 或其他定时任务来定期运行 `run_gc.py`。
- [ ] **数据库备份**: 为你的数据库文件（如果是 SQLite）或数据库服务器建立定期的备份策略。
