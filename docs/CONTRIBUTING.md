# 贡献指南

欢迎您贡献代码到 `Trans-Hub` 项目！本指南将帮助您了解如何参与项目开发。

## 1. 贡献方式

您可以通过以下方式为 `Trans-Hub` 做出贡献：

- 报告错误和提出功能请求
- 修复错误和实现新功能
- 改进文档
- 编写测试
- 翻译文档

## 2. 开发环境设置

### 2.1 克隆仓库

```bash
git clone https://github.com/your-org/trans-hub.git
cd trans-hub
```

### 2.2 创建虚拟环境

```bash
# 使用 virtualenv
virtualenv venv
source venv/bin/activate  # Linux/Mac
# 或
venv\Scripts\activate  # Windows

# 或使用 conda
conda create -n trans-hub python=3.9
conda activate trans-hub
```

### 2.3 安装依赖

```bash
# 安装开发依赖
pip install -e .[dev]
```

### 2.4 配置开发环境

```bash
# 复制示例配置文件
cp .env.example .env

# 编辑 .env 文件，设置必要的环境变量
# 例如：数据库连接字符串、API 密钥等
```

## 3. 开发规范

### 3.1 代码风格

- 遵循 PEP 8 编码规范
- 使用类型注解
- 编写清晰的文档字符串
- 保持代码简洁明了

### 3.2 提交规范

- 提交信息应当清晰、简洁，描述所做的更改
- 使用 imperative mood（命令式语气），例如 "Fix bug" 而不是 "Fixed bug" 或 "Fixes bug"
- 对于重大更改，提供更详细的描述

### 3.3 分支策略

- 使用 `main` 分支作为稳定分支
- 开发新功能或修复错误时，创建新的分支
- 分支命名应当描述性强，例如 `feature/add-new-engine` 或 `bugfix/fix-translation-error`

## 4. 开发流程

### 4.1 开发新功能

1. 创建新的分支
2. 实现功能
3. 编写测试
4. 更新文档
5. 提交代码
6. 创建 Pull Request

### 4.2 修复错误

1. 创建新的分支
2. 定位并修复错误
3. 编写测试验证修复
4. 提交代码
5. 创建 Pull Request

## 5. 引擎开发指南

有关如何开发新的翻译引擎，请参阅 [开发引擎指南](guides/creating_an_engine.rst)。

## 6. 文档改进

- 文档使用 Markdown 和 reStructuredText 编写
- 保持文档更新与代码同步
- 提供清晰、简洁的说明
- 添加示例代码以帮助用户理解

## 7. 测试

### 7.1 运行测试

```bash
# 运行所有测试
pytest

# 运行特定测试
pytest tests/test_engine.py

# 生成测试覆盖率报告
pytest --cov=trans_hub
```

### 7.2 编写测试

- 为新功能编写单元测试和集成测试
- 确保测试覆盖主要功能和边缘情况
- 保持测试独立、可重复

## 8. Pull Request 流程

1. 确保您的分支是最新的
2. 确保所有测试通过
3. 确保代码风格符合要求
4. 创建 Pull Request，描述所做的更改
5. 回应代码审查的反馈
6. 等待 Pull Request 被合并

## 9. 社区行为准则

参与 `Trans-Hub` 社区时，请遵守以下行为准则：

- 尊重他人
- 保持专业
- 对建设性的反馈持开放态度
- 专注于项目的最佳利益

## 10. 联系我们

如果您有任何问题或需要帮助，可以通过以下方式联系我们：

- GitHub Issues: https://github.com/your-org/trans-hub/issues
- 邮件列表: trans-hub@example.com
- Discord: https://discord.gg/trans-hub

感谢您的贡献！