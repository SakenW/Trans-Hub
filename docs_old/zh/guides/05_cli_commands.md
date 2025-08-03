# Trans-Hub CLI 命令参考指南

## 简介
Trans-Hub 提供了强大的命令行工具，用于管理和操作翻译服务。本指南详细介绍了所有可用的 CLI 命令及其参数。

## 主命令

### 版本信息
显示当前 Trans-Hub CLI 的版本信息。

```bash
trans-hub --version
# 或
trans-hub -v
```

## 子命令

### app
应用主入口。详细功能请参考 app 子模块文档。

```bash
trans-hub app [子命令]
```

### worker
启动 Trans-Hub Worker 进程，处理待翻译任务。

**参数**:
- `--lang`, `-l`: 要处理的语言列表（可选）
- `--batch-size`, `-b`: 每批处理的任务数量，默认值为 10
- `--poll-interval`, `-p`: 轮询间隔（秒），默认值为 5.0

**示例**:
```bash
# 启动 Worker 进程，处理所有语言的任务
trans-hub worker

# 启动 Worker 进程，只处理英语和中文任务
trans-hub worker --lang en zh

# 自定义批处理大小为 20，轮询间隔为 10 秒
trans-hub worker --batch-size 20 --poll-interval 10
```

### request
提交一个新的翻译请求到队列中。

**参数**:
- `text`: 要翻译的文本内容（必需参数）
- `--target`, `-t`: 目标语言列表（必需参数）
- `--source`, `-s`: 源语言（可选，自动检测）
- `--business-id`, `-b`: 业务ID（可选）
- `--force`, `-f`: 强制重新翻译，即使已有结果（可选）

**示例**:
```bash
# 提交翻译请求，将文本翻译为法语和西班牙语
trans-hub request "Hello world" --target fr es

# 指定源语言为英语
trans-hub request "Hello world" --target fr es --source en

# 添加业务ID并强制重新翻译
trans-hub request "Hello world" --target fr es --business-id marketing --force
```

### gc
执行数据库垃圾回收，清理过期的、无关联的旧数据。

**参数**:
- `--retention-days`, `-r`: 保留天数，默认值为 90
- `--dry-run`, `-d`: 仅预览，不执行删除（可选）

**示例**:
```bash
# 执行垃圾回收，保留最近 90 天的数据
trans-hub gc

# 自定义保留天数为 30 天
trans-hub gc --retention-days 30

# 仅预览垃圾回收结果，不实际删除数据
trans-hub gc --dry-run
```

### db-migrate
执行数据库迁移。

**参数**:
- `--database-url`, `-u`: 数据库 URL（可选，默认使用配置文件中的值）

**示例**:
```bash
# 使用配置文件中的数据库 URL 执行迁移
trans-hub db-migrate

# 指定自定义数据库 URL
trans-hub db-migrate --database-url sqlite:///custom.db
```
