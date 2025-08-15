#!/bin/bash
# run_tests.sh (v3.0.0 简化版)
#
# 本脚本仅作为 `poetry run pytest` 的快捷方式。
# 所有环境变量应在 .env.test 文件中正确配置，并由 pytest-dotenv 自动加载。
# 不再需要手动处理 PGPASSWORD 或任何其他环境变量。

set -e
echo "🚀 Running tests with configuration from .env.test..."
poetry run pytest "$@"