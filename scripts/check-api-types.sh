#!/bin/sh
# 兼容入口：契约链已收敛到 scripts/check-contracts.sh。
set -e
exec "$(git rev-parse --show-toplevel)/scripts/check-contracts.sh" "$@"
