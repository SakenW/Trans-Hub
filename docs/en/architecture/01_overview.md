graph TD
    subgraph "上层应用 (User Application)"
        A["异步应用逻辑 (e.g., FastAPI)"]
        G[".env 文件"]
    end

    subgraph "核心库: Trans-Hub"
        B["<b>主协调器 (Coordinator)</b><br/>编排工作流、应用策略"]
        U1["<b>配置模型 (TransHubConfig)</b><br/>单一事实来源"]
        D["<b>持久化处理器 (PersistenceHandler)</b><br/>数据库 I/O 抽象<br/><i>(内置并发写锁)</i>"]
        F["统一数据库 (SQLite)"]
        
        subgraph "插件化引擎子系统"
            E_meta["<b>引擎元数据注册表 (meta.py)</b><br/>解耦中心"]
            C3["<b>引擎加载器 (engine_registry.py)</b><br/>动态发现"]
            E_impl["<b>引擎实现</b><br/>(e.g., OpenAIEngine)"]
        end

        subgraph "核心机制"
            C1["内存缓存 (Cache)"]
            C2["重试/速率限制"]
        end
    end

    G -- "加载环境变量" --> U1
    A -- "创建" --> U1
    A -- "实例化并调用" --> B
    
    B -- "使用" --> C1 & C2
    B -- "依赖于" --> D
    
    subgraph "初始化/发现流程"
        style C3 fill:#e6f3ff,stroke:#36c
        style E_impl fill:#e6f3ff,stroke:#36c
        style E_meta fill:#e6f3ff,stroke:#36c
        
        U1 -- "1. 查询配置类型" --> E_meta
        B -- "2. 使用引擎名查询" --> C3
        C3 -- "3. 导入模块, 触发" --> E_impl
        E_impl -- "4. 自我注册 Config" --> E_meta
    end
    
    D -- "操作" --> F


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

