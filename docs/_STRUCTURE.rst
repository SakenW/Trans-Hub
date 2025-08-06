.. # docs/_STRUCTURE.rst
.. default-role:: literal

=======================================
Trans-Hub 文档系统结构规划 (v5 - Final)
=======================================

本文档是 Trans-Hub 帮助文档的最终结构规划蓝图，是我们所有文档工作的“宪章”和导航地图。
它不应被构建到最终的 HTML 输出中。

.. code-block:: text

    docs/
    │
    ├── 📂 source/  (【核心】所有文档源文件)
    │   │
    │   ├── 📄 index.rst  (【主入口】文档首页，包含所有章节的 toctree 导航)
    │   │
    │   ├── 📂 01_getting_started/  (【第一部分】入门指南)
    │   │   ├── 📄 index.rst            (章节介绍页，引导用户选择路径)
    │   │   ├── 📄 installation.rst      (安装指南：pip, poetry, extras, .env 配置)
    │   │   └── 📄 quickstart.rst        (快速上手：CLI 和 Python 的“Hello World”示例)
    │   │
    │   ├── 📂 02_philosophy_and_concepts/  (【第二部分】设计与概念)
    │   │   ├── 📄 index.rst            (章节介绍页)
    │   │   ├── 📄 philosophy.rst       (设计哲学：持久化优先、异步原生等“Why”的阐述)
    │   │   ├── 📄 architecture.rst     (架构概述：包含 Mermaid 架构图，解释分层和解耦)
    │   │   ├── 📄 data_model.rst       (数据库模型：ERD 图和每个核心表的职责详解)
    │   │   └── 📄 key_concepts.rst     (关键概念：深入解析稳定 ID、结构化载荷、上下文)
    │   │
    │   ├── 📂 03_practical_guides/  (【第三部分】实践指南)
    │   │   ├── 📄 index.rst            (章节介绍页，列出所有实用场景)
    │   │   ├── 📄 python_embedding_guide.rst (Python 嵌入指南：API 的标准用法和模式)
    │   │   ├── 📄 cli_usage_guide.rst    (CLI 使用指南：面向场景的 CLI 工作流示例)
    │   │   ├── 📄 cicd_integration.rst   (CI/CD 集成模式：如何自动化翻译流程)
    │   │   ├── 📄 handling_rich_text.rst (高级技巧：如何处理 HTML 或多字段内容)
    │   │   └── 📄 filesystem_integration.rst (高级技巧：读写 JSON/YAML 翻译文件)
    │   │
    │   ├── 📂 04_operations_and_deployment/  (【第四部分】部署与运维)
    │   │   ├── 📄 index.rst            (章节介绍页)
    │   │   ├── 📄 configuration.rst    (配置详解：TransHubConfig 的所有参数说明)
    │   │   ├── 📄 deployment_guide.rst   (部署指南：生产环境部署步骤、systemd 配置)
    │   │   ├── 📄 database_management.rst (数据库管理：后端选择、备份与恢复策略)
    │   │   ├── 📄 monitoring_and_alerts.rst (监控告警：关键指标和 SQL 查询示例)
    │   │   └── 📄 troubleshooting_and_dlq.rst (故障排查：常见问题、日志解读、DLQ 处理)
    │   │
    │   ├── 📂 05_deep_dive/  (【第五部分】深入组件)
    │   │   ├── 📄 index.rst            (章节介绍页)
    │   │   ├── 📄 coordinator.rst      (深入解析：Coordinator 的内部工作流)
    │   │   ├── 📄 persistence_layer.rst (深入解析：持久化层的设计与并发安全)
    │   │   ├── 📄 translation_engines.rst (深入解析：引擎基类与生命周期)
    │   │   └── 📄 processing_policy.rst  (深入解析：重试、缓存和批处理的策略)
    │   │
    │   ├── 📂 06_reference/  (【第六部分】参考)
    │   │   ├── 📄 index.rst            (章节介绍页)
    │   │   ├── 📂 api/                  (Python API 自动文档)
    │   │   │   ├── 📄 index.rst        (API 参考主页)
    │   │   │   ├── 📂 core/            (核心契约 API)
    │   │   │   │   └── ... (types.rst, exceptions.rst, interfaces.rst)
    │   │   │   └── 📂 components/      (具体组件 API)
    │   │   │       └── ... (coordinator.rst, config.rst, engines.rst)
    │   │   └── 📄 cli_reference.rst    (CLI 参考：每个命令的参数和选项的权威列表)
    │   │
    │   ├── 📂 07_project_and_contribution/  (【第七部分】项目与贡献)
    │   │   ├── 📄 index.rst            (章节介绍页)
    │   │   ├── 📄 roadmap.rst          (项目路线图：v3.x, v4.0 的史诗规划)
    │   │   ├── 📄 contribution_guide.rst (贡献指南：PR 流程、行为准则)
    │   │   ├── 📄 development_setup.rst (开发环境搭建：Poetry, Ruff, Mypy)
    │   │   ├── 📄 testing_strategy.rst   (测试策略：单元 vs 集成，如何写测试)
    │   │   ├── 📄 creating_an_engine.rst (教程：如何开发一个新的翻译引擎)
    │   │   ├── 📄 multilingual.rst     (教程：如何为文档贡献翻译)
    │   │   └── 📄 release_process.rst    (SOP：项目维护者的发布流程)
    │   │
    │   └── 📂 appendix/  (【附录】)
    │       ├── 📄 index.rst            (章节介绍页)
    │       ├── 📄 faq.rst              (常见问题解答)
    │       ├── 📄 changelog.rst        (【自动化】由 sphinx-changelog 从 git 历史生成)
    │       └── 📄 license.rst          (项目许可协议)
    │
    ├── 📂 locale/  (【国际化】多语言翻译文件)
    │   └── ...
    │
    ├── 📂 changelog.d/  (【自动化】存放变更日志片段)
    │   └── 📂 unreleased/
    │       └── 📄 .keep (占位文件)
    │
    ├── 📄 conf.py  (【配置】Sphinx 主配置文件，已升级)
    ├── 📄 Makefile  (【构建】Linux/macOS 构建脚本，已升级)
    ├── 📄 make.bat  (【构建】Windows 构建脚本，已升级)
    └── 📄 requirements.txt  (【依赖】文档构建所需的 Python 包)