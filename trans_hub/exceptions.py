# trans_hub/exceptions.py
"""
本模块定义了 Trans-Hub 项目中所有自定义的、语义化的异常类型。

使用自定义异常可以使错误处理更加精确和清晰，方便上层调用者根据
不同的错误类型执行不同的处理逻辑。
"""


class TransHubError(Exception):
    """
    所有 Trans-Hub 自定义异常的通用基类。
    捕获此异常可以处理所有源自本项目的预期错误。
    """
    pass


class ConfigurationError(TransHubError):
    """
    表示在加载、解析或验证配置时发生的错误。
    例如，.env 文件缺失关键字段，或配置值格式不正确。
    """
    pass


class EngineNotFoundError(TransHubError, KeyError):
    """
    表示尝试访问一个未注册或不可用的翻译引擎时引发的错误。
    继承自 KeyError 是为了保持与字典查找行为的一致性。
    """
    pass


class DatabaseError(TransHubError):
    """
    表示在持久化层操作（如数据库连接、查询）中发生的错误。
    通常是底层数据库驱动异常的包装。
    """
    pass


class APIError(TransHubError):
    """
    表示与外部翻译服务 API 交互时发生的错误。
    例如，网络问题、API 密钥无效或服务返回错误状态码。
    """
    pass