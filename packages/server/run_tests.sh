#!/bin/bash

# run_tests.sh

# 从 .env.test 文件中安全地读取密码
export PGPASSWORD=$(grep -E '^TH_DATABASE_URL=' .env.test | cut -d'@' -f1 | cut -d':' -f3)

# 运行 pytest，可以传递其他参数，例如指定特定文件
poetry run pytest "$@"