#!/usr/bin/env bash
set -euo pipefail
poetry run pytest "$@"

# run_tests.sh

# 从 .env.test 文件中安全地读取密码
# 注意：这个脚本比较脆弱，如果URL格式改变，可能需要调整
export PGPASSWORD="$(
python - <<'PY'
from urllib.parse import urlparse
import os, re, sys
s = open('.env.test','r',encoding='utf-8').read()
m = re.search(r'^TRANSHUB_MAINTENANCE_DATABASE_URL=["\']?([^"\']+)', s, re.M)
if not m: sys.exit(0)
print(urlparse(m.group(1)).password or "")
PY
)"
# 运行 pytest，可以传递其他参数，例如指定特定文件
poetry run pytest "$@"

# 清理环境变量，避免泄露到当前shell
unset PGPASSWORD