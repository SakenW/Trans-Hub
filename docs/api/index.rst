.. # docs/api/index.rst

==========
API 参考
==========

本部分包含了 `trans_hub` 核心库的完整 API 参考。所有文档均基于源代码中的中文文档字符串 (Docstrings) 自动生成。

.. toctree::
   :maxdepth: 2
   :caption: 核心编排与配置

   coordinator
   config

.. toctree::
   :maxdepth: 2
   :caption: 核心契约 (trans_hub.core)

   core_types
   core_exceptions
   core_interfaces

.. toctree::
   :maxdepth: 2
   :caption: 插件与扩展

   engines

.. note::
   为了反映 v3.0 的新架构，核心的类型、异常和接口定义已移至 `core_*` 页面。`persistence_impl` 页面描述了内置的 `SQLite` 实现。