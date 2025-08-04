.. # docs/api/exceptions.rst

=========================
自定义异常 (Exceptions)
=========================

.. currentmodule:: trans_hub.core.exceptions

`Trans-Hub` 定义了一系列语义化的自定义异常，以便进行精确的错误处理。所有自定义异常都继承自基类 ``TransHubError``，这使得捕获所有项目相关的预期错误变得简单。

异常基类
--------

.. autoclass:: TransHubError
   :show-inheritance:

   所有 `Trans-Hub` 自定义异常的通用基类。

具体异常类型
------------

### 配置相关异常

.. autoclass:: ConfigurationError
   :show-inheritance:
   
   表示在加载、解析或验证配置时发生的错误。例如，`.env` 文件缺失关键字段，或配置值格式不正确。

### 引擎相关异常

.. autoclass:: EngineNotFoundError
   :show-inheritance:

   当尝试访问一个未在系统中注册或不可用的翻译引擎时引发。

.. autoclass:: APIError
   :show-inheritance:

   表示与外部翻译服务 API 交互时发生的通用错误。例如，网络问题、API 服务返回错误状态码等。

### 持久化相关异常

.. autoclass:: DatabaseError
   :show-inheritance:

   表示在持久化层操作（如数据库连接、查询）中发生的错误。通常是底层数据库驱动异常的包装。

异常处理示例
------------

以下是如何精确捕获和处理 `Trans-Hub` 异常的示例代码：

.. code-block:: python

   from trans_hub import Coordinator
   from trans_hub.exceptions import (
       TransHubError, 
       ConfigurationError, 
       APIError, 
       DatabaseError
   )

   # config = ...
   # handler = ...
   # coordinator = Coordinator(config, handler)

   try:
       # 尝试执行一个可能失败的操作
       async for result in coordinator.process_pending_translations("zh-CN"):
           # ...
           pass

   except ConfigurationError as e:
       # 处理配置错误，这通常是启动时的问题
       print(f"配置错误，请检查您的 .env 文件或配置对象: {e}")

   except APIError as e:
       # 处理与外部 API 的通信错误，可能需要稍后重试
       print(f"翻译引擎 API 错误: {e}")

   except DatabaseError as e:
       # 处理数据库连接或查询错误
       print(f"数据库错误: {e}")

   except TransHubError as e:
       # 捕获任何其他未明确处理的 Trans-Hub 异常
       print(f"发生了一个未指定的 Trans-Hub 错误: {e}")
       
   except Exception as e:
       # 捕获所有其他意外错误
       print(f"发生了一个未知错误: {e}")