# **Architecture Overview: Trans-Hub v2.2**

The target audience of this document: core maintainers, community contributors, and users who wish to gain a deeper understanding of the internal workings of `Trans-Hub`.

**Document Purpose**: This document aims to provide a high-level overview of the `Trans-Hub` system architecture, design principles, and core workflows. It serves as a starting point for understanding "how the system works.

[Return to Document Index](../INDEX.md)

It seems there is no text provided for translation. Please provide the text you would like to have translated.

## **1. Design Philosophy and Core Principles**

### **1.1 Project Positioning**

Trans-Hub is an **asynchronous-first**, embeddable Python application with persistent storage, serving as an intelligent localization (i18n) backend engine. It aims to unify and simplify multilingual translation workflows, providing efficient, low-cost, and highly reliable translation capabilities for upper-layer applications through intelligent caching, pluggable translation engines, and robust error handling and policy control.

### **1.2 Core Engineering Principles**

- **Async-First**: The entire core library is designed to be purely asynchronous to achieve maximum I/O concurrency performance and to seamlessly integrate with modern asynchronous web frameworks like FastAPI.
- **Clear Separation of Concerns**: Each component has a highly cohesive responsibility. `PersistenceHandler` only manages the database, `Engine` only handles translation logic, and `Coordinator` only orchestrates workflows.
- **Dependency Injection**: Core components receive their dependencies in their constructors, allowing for loose coupling between components, making them easy to test and replace.
- **Contract First**: All module interactions are constrained by strict DTOs (using Pydantic) and interfaces (`typing.Protocol`).
- **Structured Configuration**: All configuration items in the system are defined and validated through Pydantic models and can be automatically loaded from environment variables or `.env` files.

It seems there is no text provided for translation. Please provide the text you would like to have translated.

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

It seems there is no text provided for translation. Please provide the text you would like to have translated.

## **3. Detailed Explanation of Core Workflow**

The following is the core workflow of `Coordinator.process_pending_translations`, which integrates memory caching, database interaction, and engine calls.

```mermaid
sequenceDiagram
    participant App as 上层应用
    participant Coord as Coordinator
    participant Cache as TranslationCache
    participant Handler as PersistenceHandler
    participant Engine as TranslationEngine

    App->>+Coord: process_pending_translations('zh-CN')  
Coord->>+Handler: stream_translatable_items('zh-CN', ...)  
Note over Handler: (Acquire write lock)<br>Transaction 1: Lock a batch of pending tasks<br>(Status->TRANSLATING)<br>(Release write lock)  
Handler-->>-Coord: yield batch_of_items

    loop for each translation batch (grouped by context)
        Coord->>+Cache: Check memory cache
        Cache-->>-Coord: cached_results, uncached_items

        If there are uncached items
            loop Retry attempts within the batch
                Note over Coord: (Apply rate limiting)
                Coord->>+Engine: atranslate_batch(uncached_items)
                Engine-->>-Coord: List<EngineBatchItemResult>
                alt There are retryable errors in the batch
                    Coord->>Coord: await asyncio.sleep(exponential backoff)
                else
                    break
                end
            end
            Coord->>+Cache: Cache new translation results
            Cache-->>-Coord: (New results have been cached)
        end

        Note over Coord: Combine all results
        Coord->>+Handler: save_translations(all_results)
        Note over Handler: (Acquire write lock)<br>Transaction 2: Atomic update of translation records<br>(Release write lock)
        Handler-->>-Coord: (Database update completed)

        loop for each final result
            Coord-->>App: yield TranslationResult
        end
    end
```

### **Concurrency Safety**

Trans-Hub" is designed for high-concurrency environments. To handle scenarios like "multiple producers (`request`) and one worker (`process_pending_translations`) simultaneously writing to the database," the `DefaultPersistenceHandler` internally implements an **asynchronous write lock (`asyncio.Lock`)**.

- All methods that execute **write transactions** (such as `ensure_pending_translations`, `save_translations`) must acquire this lock before execution.
- This ensures that write operations to the database are **atomic and serial**, fundamentally avoiding transaction conflicts and data races.
- **Read-only** operations (such as `get_translation`) **do not** acquire this lock, allowing them to be executed concurrently with ongoing write operations (thanks to SQLite's WAL mode), maximizing read performance.

It seems there is no text provided for translation. Please provide the text you would like to have translated.

## **4. Scalability**

The design of `Trans-Hub` provides high scalability in two key dimensions:

1.  **Translation Capability**: By adding new files in the `trans_hub/engines/` directory, you can easily integrate any third-party translation service.
    > _See [Guide: Developing a New Engine](../contributing/developing_engines.md)_
2.  **Storage Backend**: By implementing the `PersistenceHandler` protocol, you can replace the default SQLite storage with any asynchronous database, such as PostgreSQL (using `asyncpg`) or MySQL.

This enables `Trans-Hub` to flexibly adapt to various needs, from small projects to large-scale, high-concurrency production environments.