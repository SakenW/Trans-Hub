.. # docs/api/config.rst

===================
配置模型 (Config)
===================

.. currentmodule:: trans_hub.config

本模块使用 Pydantic 定义了 Trans-Hub 项目的主配置模型和相关的子模型。

主要配置
----------

.. autoclass:: TransHubConfig
   :members:
   :undoc-members:
   :show-inheritance:
   :inherited-members: BaseSettings

引擎名称枚举
------------
.. autoclass:: EngineName
   :members:
   :undoc-members:

其他配置模型
--------------

.. autoclass:: LoggingConfig
   :members:
   :undoc-members:
   :show-inheritance:

.. autoclass:: RetryPolicyConfig
   :members:
   :undoc-members:
   :show-inheritance: