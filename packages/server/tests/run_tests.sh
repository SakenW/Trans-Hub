#!/bin/bash

# run_tests.sh

# 从 .env.test 文件中安全地读取密码
# 注意：这个脚本比较脆弱，如果URL格式改变，可能需要调整
export PGPASSWORD=$(grep -E '^TH_DATABASE_URL=' .env.test | cut -d'@' -f1 | cut -d':' -f3)

# 运行 pytest，可以传递其他参数，例如指定特定文件
poetry run pytest "$@"

# 清理环境变量，避免泄露到当前shell
unset PGPASSWORD