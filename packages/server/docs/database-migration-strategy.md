# 数据库迁移策略文档

## 概述

本文档描述了 Trans-Hub 项目中实施的数据库迁移策略，特别是**版本表与业务表分离**的解决方案。

## 问题背景

在多租户或多 schema 的数据库架构中，传统的 Alembic 迁移存在以下问题：

1. **版本表污染**：`alembic_version` 表默认会在每个业务 schema 中创建
2. **迁移状态混乱**：多个 schema 中的版本表可能导致迁移状态不一致
3. **管理复杂性**：需要为每个 schema 单独管理迁移历史

## 解决方案：版本表分离策略

### 核心思想

- **版本表统一管理**：将 `alembic_version` 表统一放置在 `public` schema 中
- **业务表分离部署**：业务表根据配置部署到指定的目标 schema 中
- **迁移状态集中**：所有 schema 的迁移状态通过统一的版本表管理

### 技术实现

#### 1. Monkey Patching 方案

通过运行时修改 `alembic.context.configure` 函数，强制将 `version_table_schema` 设置为 `None`：

```python
def _apply_version_table_separation_strategy(self, alembic_cfg: AlembicConfig) -> None:
    """应用版本表分离策略
    
    通过 monkey patching 强制 alembic_version 表创建在 public schema 中，
    而业务表根据配置创建在目标 schema 中。
    """
    import alembic.context
    
    original_configure = alembic.context.configure
    
    def patched_configure(*args, **kwargs):
        # 强制版本表在 public schema
        kwargs['version_table_schema'] = None
        return original_configure(*args, **kwargs)
    
    alembic.context.configure = patched_configure
```

#### 2. 应用位置

该策略在以下位置被应用：

- **生产迁移**：<mcfile name="db_service.py" path="src/trans_hub/infrastructure/db/db_service.py"></mcfile> 中的 `run_migrations` 方法
- **测试环境**：<mcfile name="conftest.py" path="tests/conftest.py"></mcfile> 中的 `run_migrations` 函数
- **管理脚本**：<mcfile name="migrate_db.py" path="src/trans_hub/management/migrate_db.py"></mcfile> 中的迁移函数

## 使用方法

### 1. 生产环境迁移

使用新的迁移管理脚本：

```bash
# 升级到最新版本
poetry run python src/trans_hub/management/migrate_db.py upgrade --revision head

# 查看迁移历史
poetry run python src/trans_hub/management/migrate_db.py history

# 降级到指定版本
poetry run python src/trans_hub/management/migrate_db.py downgrade --revision <revision_id>

# 指定目标 schema（默认为 'th'）
poetry run python src/trans_hub/management/migrate_db.py upgrade --schema custom_schema
```

### 2. 开发环境迁移

通过 CLI 命令：

```bash
# 在 src 目录下执行
cd src
python -m trans_hub.adapters.cli.main db migrate
```

### 3. 测试环境

测试环境会自动应用版本表分离策略，无需额外配置。

## 数据库支持

### PostgreSQL

- ✅ 完全支持 schema 分离
- ✅ 自动创建目标 schema
- ✅ 版本表在 `public` schema，业务表在目标 schema

### SQLite

- ✅ 兼容性支持
- ⚠️ 不支持 schema 概念，所有表在同一命名空间
- ✅ 版本表分离策略仍然生效（逻辑层面）

## 迁移脚本特性

### 智能数据库检测

迁移脚本会自动检测数据库类型并采用相应策略：

```python
def ensure_target_schema(engine: Engine, schema_name: str) -> None:
    """确保目标 schema 存在（仅适用于 PostgreSQL）"""
    dialect_name = engine.dialect.name
    
    if dialect_name == 'postgresql':
        # PostgreSQL: 创建 schema
        with engine.connect() as conn:
            conn.execute(text(f"CREATE SCHEMA IF NOT EXISTS {schema_name}"))
            conn.commit()
    elif dialect_name == 'sqlite':
        # SQLite: 跳过 schema 创建
        logger.info(f"SQLite 数据库不支持 schema，跳过 schema '{schema_name}' 的创建")
    else:
        logger.warning(f"未知数据库类型 '{dialect_name}'，跳过 schema 创建")
```

### 版本表管理

自动处理 `alembic_version` 表的创建和验证：

```python
def ensure_version_table_in_public(engine: Engine) -> None:
    """确保 alembic_version 表在 public schema 中存在"""
    dialect_name = engine.dialect.name
    
    with engine.connect() as conn:
        if dialect_name == 'postgresql':
            # PostgreSQL: 检查 information_schema.tables
            result = conn.execute(text("""
                SELECT table_name FROM information_schema.tables 
                WHERE table_name = 'alembic_version' AND table_schema = 'public'
            """))
        elif dialect_name == 'sqlite':
            # SQLite: 检查 sqlite_master
            result = conn.execute(text("""
                SELECT name FROM sqlite_master 
                WHERE type = 'table' AND name = 'alembic_version'
            """))
        
        if result.fetchone():
            logger.info("alembic_version 表已存在")
        else:
            logger.info("alembic_version 表不存在，将由 Alembic 自动创建")
```

## 配置要求

### 环境变量

迁移脚本使用标准的配置加载机制：

```python
config = load_config_with_validation("prod")
```

### Alembic 配置

确保 `alembic.ini` 中包含必要的配置：

```ini
[alembic]
script_location = alembic
db_schema = th
```

## 验证和测试

### 验证迁移结果

迁移完成后，可以通过以下 SQL 验证表的分布：

```sql
-- PostgreSQL: 检查表分布
SELECT schemaname, tablename 
FROM pg_tables 
WHERE tablename IN ('alembic_version') 
   OR schemaname = 'th';

-- SQLite: 检查所有表
SELECT name FROM sqlite_master WHERE type = 'table';
```

### 测试覆盖

- ✅ 单元测试：版本表分离逻辑
- ✅ 集成测试：完整迁移流程
- ✅ 多数据库测试：PostgreSQL 和 SQLite

## 故障排除

### 常见问题

1. **SQLite 中的 information_schema 错误**
   - 原因：SQLite 不支持 `information_schema`
   - 解决：使用 `sqlite_master` 表查询

2. **PostgreSQL 连接失败**
   - 检查连接字符串格式
   - 确认数据库服务可访问
   - 验证用户权限

3. **Schema 创建失败**
   - 确认用户具有 `CREATE SCHEMA` 权限
   - 检查目标 schema 是否已存在

### 调试模式

迁移脚本提供详细的日志输出：

```bash
# 查看详细迁移过程
poetry run python src/trans_hub/management/migrate_db.py upgrade --revision head
```

## 最佳实践

1. **备份优先**：在生产环境执行迁移前，务必备份数据库
2. **测试验证**：在测试环境充分验证迁移脚本
3. **监控日志**：关注迁移过程中的警告和错误信息
4. **版本管理**：使用版本控制管理迁移脚本的变更

## 未来改进

- [ ] 支持更多数据库类型（MySQL、Oracle 等）
- [ ] 提供迁移回滚的安全检查
- [ ] 集成数据库备份和恢复功能
- [ ] 支持并行迁移和分片数据库

---

*最后更新：2025-08-23*
*版本：1.0.0*