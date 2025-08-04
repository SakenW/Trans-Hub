.. # docs/guides/architecture.rst

==================
Trans-Hub 架构概述
==================

:文档目的: 本文档旨在提供一个关于 `Trans-Hub v3.0` 系统架构、设计原则和核心工作流程的概览。

设计哲学与核心原则
--------------------

`Trans-Hub v3.0` 的架构遵循以下核心原则：

- **异步优先**: 整个核心库被设计为纯异步。
- **分层与解耦**: 通过`核心(core)`包、服务层抽象和可插拔的持久化/引擎层，实现高度解耦。
- **稳定引用**: 通过 `business_id` 将内容的身份与其具体值分离。
- **结构化优先**: 原生支持 JSON 格式的结构化内容。
- **配置与实现分离**: 核心配置不依赖于具体实现，提高了系统的可扩展性。

系统架构
--------

.. mermaid::

   graph TD
       subgraph "应用层 (Application Layer)"
           CLI["CLI (Typer)"]
           WebApp["Web App (e.g., FastAPI)"]
       end

       subgraph "核心库: Trans-Hub"
           Coordinator["<b>主协调器 (Coordinator)</b><br/>编排工作流、应用策略"]
           Config["<b>配置 (Config)</b><br/>加载原始配置"]
           
           subgraph "核心契约 (trans_hub.core)"
               style Core fill:#e6f3ff,stroke:#36c
               CoreTypes["<b>核心类型 (types.py)</b><br/>Pydantic DTOs"]
               CoreInterfaces["<b>接口 (interfaces.py)</b><br/>PersistenceHandler Protocol"]
               CoreExceptions["<b>异常 (exceptions.py)</b>"]
           end

           subgraph "服务与策略"
                Policies["处理策略 (ProcessingPolicy)"]
                Cache["内存缓存 (Cache)"]
           end

           subgraph "可插拔层 (Pluggable Layers)"
               Persistence["<b>持久化层 (Persistence)</b><br/>(SQLite 实现)"]
               Engines["<b>引擎层 (Engines)</b><br/>(Debug, OpenAI...)"]
           end
           
           DB["数据库 (SQLite)"]
       end

       CLI & WebApp --> Coordinator
       Coordinator -- uses --> Policies & Cache
       Coordinator -- depends on --> CoreInterfaces
       Policies -- depends on --> CoreTypes
       
       Persistence -- implements --> CoreInterfaces
       Persistence -- interacts with --> DB
       
       Coordinator -- uses --> Engines
       Engines -- depends on --> CoreTypes & CoreExceptions

       Config --> Coordinator