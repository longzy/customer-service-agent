#!/bin/sh
# 停止本地 dev.sh 启动的 3000/3001/8000 监听进程；只按端口，不触碰其他服务。
set -e
for port in 3000 3001 8000; do
  pids=$(lsof -tiTCP:"$port" -sTCP:LISTEN 2>/dev/null || true)
  if [ -n "$pids" ]; then
    echo "停止 $port：$pids"
    # shellcheck disable=SC2086
    kill $pids
  else
    echo "$port 空闲"
  fi
done
