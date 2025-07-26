# **Architecture Overview: Trans-Hub v2.2**

The target audience of this document: core maintainers, community contributors, and users who wish to gain a deeper understanding of the internal workings of `Trans-Hub`.

**Document Purpose**: This document aims to provide a high-level overview of the `Trans-Hub` system architecture, design principles, and core workflows. It serves as a starting point for understanding "how the system works.

[Return to Document Index](../INDEX.md)

---

## **1. 设计哲学与核心原则**

### **1.1 项目定位**

`Trans-Hub` 是一个**异步优先**、可嵌入 Python 应用程序的、带持久化存储的智能本地化（i18n）后端引擎。它旨在统一和简化多语言翻译工作流，通过智能缓存、可插拔的翻译引擎、以及健壮的错误处理和策略控制，为上层应用提供高效、低成本、高可靠的翻译能力。

### **1.2 核心工程原则**

- **异步优先 (Async-First)**: 整个核心库被设计为纯异步，以实现最大的 I/O 并发性能，并与现代异步 Web 框架（如 FastAPI）无缝集成。
- **职责明确 (Clear Separation of Concerns)**: 各组件职责高度内聚。`PersistenceHandler` 只管理数据库，`Engine` 只处理翻译逻辑，`Coordinator` 只负责编排工作流。
- **依赖注入 (Dependency Injection)**: 核心组件在其构造函数中接收其依赖，使得组件之间松耦合，易于测试和替换。
- **契约优先 (Contract First)**: 所有模块交互都通过严格的 DTOs (使用 Pydantic) 和接口 (`typing.Protocol`) 进行约束。
- **结构化配置 (Structured Configuration)**: 系统的所有配置项均通过 Pydantic 模型进行定义和验证，并能自动从环境变量或 `.env` 文件加载。

---

## **2. System Architecture**

Trans-Hub" adopts a modular layered architecture and a **dependency inversion** registration model, ensuring that each component has a single responsibility and is highly decoupled.

```mermaid
graph TD
    subgraph "上层应用 (User Application)"
        A["异步应用逻辑 (e.g., FastAPI)"]
        G[".env 文件"]
    end

    subgraph "Core Library: Trans-Hub"
        B["<b>Main Coordinator</b><br/>Orchestrates workflows, applies strategies"]
        U1["<b>Configuration Model (TransHubConfig)</b><br/>Single source of truth"]
        D["<b>Persistence Handler</b><br/>Database I/O abstraction<br/><i>(Built-in concurrent write lock)</i>"]
        F["Unified Database (SQLite)"]
        
        subgraph "Plugin Engine Subsystem"
            E_meta["<b>Engine Metadata Registry (meta.py)</b><br/>Decoupling center"]
            C3["<b>Engine Loader (engine_registry.py)</b><br/>Dynamic discovery"]
            E_impl["<b>Engine Implementation</b><br/>(e.g., OpenAIEngine)"]
        end

        subgraph "Core Mechanism"
            C1["Memory Cache"]
            C2["Retry/Rate Limiting"]
        end
    end

    G -- "Load environment variables" --> U1  
A -- "Create" --> U1  
A -- "Instantiate and call" --> B  

B -- "Use" --> C1 & C2  
B -- "Depends on" --> D  

subgraph "Initialization/Discovery Process"  
    style C3 fill:#e6f3ff,stroke:#36c  
    style E_impl fill:#e6f3ff,stroke:#36c  
    style E_meta fill:#e6f3ff,stroke:#36c  

    U1 -- "1. Query configuration type" --> E_meta  
    B -- "2. Query using engine name" --> C3  
    C3 -- "3. Import module, trigger" --> E_impl  
    E_impl -- "4. Self-register Config" --> E_meta  
end  

D -- "Operate" --> F

### **Component Responsibilities**

- **`Coordinator`**: **The brain of the business process**. It is the only entry point for upper-level applications to interact with it. It is responsible for orchestrating all operations: receiving requests, applying retry/rate limiting strategies, calling the engine, handling caching, and storing results in the database.
- **`PersistenceHandler`**: **The gatekeeper of the database**. It is an abstract interface that defines all database read and write operations. Its default implementation, `DefaultPersistenceHandler`, is based on `aiosqlite` and ensures transactional safety for all write operations through an **internal asynchronous write lock**, allowing it to work stably even under multiple concurrent Workers and API requests.
- **`BaseTranslationEngine`**: **The plugin slot for translation capabilities**. It defines the contract that all translation engines must adhere to, with the core being the implementation of the `_atranslate_one` asynchronous method.
- **`TransHubConfig`**: **The control panel of the system**. It is a Pydantic model that centralizes all configuration items and is dynamically populated by the `Coordinator` during initialization.
- **Engine discovery and registration mechanism**:
  - `engine_registry.py` is responsible for **discovering and loading** the **implementation code** of the engines (`...Engine` classes).
  - `engines/meta.py` is responsible for maintaining a mapping from engine names to their **configuration models** (`...Config` classes).
  - This dual registry system completely decouples the configuration system from the engine implementation, avoiding circular dependencies.

---

## **3. 核心工作流详解**

以下是 `Coordinator.process_pending_translations` 的核心工作流，它整合了内存缓存、数据库交互和引擎调用。

```mermaid
sequenceDiagram
    participant App as 上层应用
    participant Coord as Coordinator
    participant Cache as TranslationCache
    participant Handler as PersistenceHandler
    participant Engine as TranslationEngine

    App->>+Coord: process_pending_translations('zh-CN')
    Coord->>+Handler: stream_translatable_items('zh-CN', ...)
    Note over Handler: (获取写锁)<br>事务1: 锁定一批待办任务<br>(状态->TRANSLATING)<br>(释放写锁)
    Handler-->>-Coord: yield batch_of_items

    loop 针对每个翻译批次 (按 context 分组)
        Coord->>+Cache: 检查内存缓存
        Cache-->>-Coord: cached_results, uncached_items

        opt 如果有未缓存的项目
            loop 批次内部的重试尝试
                Note over Coord: (应用速率限制)
                Coord->>+Engine: atranslate_batch(uncached_items)
                Engine-->>-Coord: List<EngineBatchItemResult>
                alt 批次中存在可重试错误
                    Coord->>Coord: await asyncio.sleep(指数退避)
                else
                    break
                end
            end
            Coord->>+Cache: 缓存新翻译结果
            Cache-->>-Coord: (新结果已缓存)
        end

        Note over Coord: 组合所有结果
        Coord->>+Handler: save_translations(all_results)
        Note over Handler: (获取写锁)<br>事务2: 原子更新翻译记录<br>(释放写锁)
        Handler-->>-Coord: (数据库更新完成)

        loop 对每个最终结果
            Coord-->>App: yield TranslationResult
        end
    end
```

### **并发安全**

`Trans-Hub` 被设计用于高并发环境。为了处理像“多个生产者 (`request`) 和一个工作者 (`process_pending_translations`) 同时对数据库进行写操作”这样的场景，`DefaultPersistenceHandler` 在其内部实现了一个**异步写锁 (`asyncio.Lock`)**。

- 所有执行**写事务**的方法（如 `ensure_pending_translations`, `save_translations`）在执行前都必须获取这个锁。
- 这确保了对数据库的写操作是**原子且串行**的，从根本上避免了事务冲突和数据竞争。
- **只读**操作（如 `get_translation`）**不会**获取这个锁，因此可以与正在进行的写操作并发执行（得益于 SQLite 的 WAL 模式），最大限度地保证了读取性能。

---

## **4. Scalability**

The design of `Trans-Hub` provides high scalability in two key dimensions:

1.  **Translation Capability**: By adding new files in the `trans_hub/engines/` directory, you can easily integrate any third-party translation service.
    > _See [Guide: Developing a New Engine](../contributing/developing_engines.md)_
2.  **Storage Backend**: By implementing the `PersistenceHandler` protocol, you can replace the default SQLite storage with any asynchronous database, such as PostgreSQL (using `asyncpg`) or MySQL.

This enables `Trans-Hub` to flexibly adapt to various needs, from small projects to large-scale, high-concurrency production environments.