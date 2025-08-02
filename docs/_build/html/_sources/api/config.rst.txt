.. # docs/api/config.rst

配置模型 (Config)
===================

.. currentmodule:: trans_hub.config

本模块使用 Pydantic 定义了 Trans-Hub 项目的主配置模型和相关的子模型。

主要配置
----------

.. autoclass:: TransHubConfig
   :members:
   :undoc-members: false
   :show-inheritance:
   :inherited-members: BaseModel

引擎名称枚举
------------
.. autoclass:: EngineName
   :members:
   :undoc-members: false
   :show-inheritance:

引擎配置集合
------------

.. autoclass:: EngineConfigs
   :members:
   :undoc-members: false
   :show-inheritance:

其他配置模型
--------------

.. autoclass:: LoggingConfig
   :members:
   :undoc-members: false
   :show-inheritance:

.. autoclass:: RetryPolicyConfig
   :members:
   :undoc-members: false
   :show-inheritance: