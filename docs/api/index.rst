.. # docs/api/index.rst

API 参考
========

本部分包含了 `trans-hub` 核心库的完整 API 参考。通过这些文档，您可以了解如何使用 Trans-Hub 的各种功能组件。

所有文档均基于源代码中的中文文档字符串 (Docstrings) 生成，并保持与代码同步更新。

使用指南
--------

- 浏览左侧导航栏，查看各个模块的详细文档
- 每个类和方法都包含详细的参数说明、返回值类型和使用示例
- 对于复杂组件，提供了完整的使用场景示例
- 异常部分说明了可能遇到的错误及处理方法

快速链接
--------

- :doc:`coordinator`：核心协调器，负责管理翻译流程
- :doc:`config`：配置类，管理系统和引擎配置
- :doc:`engines`：翻译引擎，支持多种翻译服务
- :doc:`types`：核心数据类型，定义了系统中的数据结构
- :doc:`persistence`：持久化层，负责数据存储和检索
- :doc:`exceptions`：自定义异常，用于错误处理

.. toctree::
   :maxdepth: 2
   :caption: 核心组件

   coordinator
   config
   types
   exceptions

.. toctree::
   :maxdepth: 2
   :caption: 插件与扩展

   engines
   persistence