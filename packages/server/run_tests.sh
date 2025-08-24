#!/bin/bash
# run_tests.sh (v3.0.0 简化版)
#
# 本脚本仅作为 `poetry run pytest` 的快捷方式。
# 所有环境变量应在 .env 文件中正确配置，测试时会自动设置 TRANSHUB_APP_ENV=test。
# 不再需要手动处理 PGPASSWORD 或任何其他环境变量。

set -e
echo "🚀 Running tests with configuration from .env..."
# 设置测试环境模式
export TRANSHUB_APP_ENV=test
poetry run pytest "$@"