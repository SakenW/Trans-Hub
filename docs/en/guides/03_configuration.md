from trans_hub.config import TransHubConfig

# 创建一个使用所有默认设置的配置对象
default_config = TransHubConfig()

# 创建一个自定义配置的对象
custom_config = TransHubConfig(
    active_engine="openai",
    source_lang="en",
    batch_size=100
)


# 使用一个位于 /var/data/ 的持久化数据库文件
config = TransHubConfig(database_url="sqlite:////var/data/my_app_translations.db")

# 使用内存数据库（仅用于测试，数据不会持久化）
config = TransHubConfig(database_url="sqlite:///:memory:")


from trans_hub.cache import CacheConfig

# 创建一个能容纳 10000 个项目、有效期为 24 小时的 LRU 缓存配置
custom_cache = CacheConfig(maxsize=10000, ttl=86400, cache_type="lru")

config = TransHubConfig(cache_config=custom_cache)


from trans_hub.config import EngineConfigs
from trans_hub.engines.openai import OpenAIEngineConfig

# 手动为 OpenAI 引擎提供一个自定义模型
openai_config = OpenAIEngineConfig(
    openai_model="gpt-4-turbo",
    # openai_api_key 会自动从 .env 加载
)

# 默认激活 translators，但同时为 openai 提供了预配置
config = TransHubConfig(
    active_engine="translators",
    engine_configs=EngineConfigs(
        openai=openai_config
    )
)


# .env
TH_OPENAI_API_KEY="sk-..."
TH_OPENAI_MODEL="gpt-4-turbo"
TH_OPENAI_TEMPERATURE="0.5"

