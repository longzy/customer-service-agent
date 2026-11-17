.DEFAULT_GOAL := help

.PHONY: help dev dev-stop dev-reset status verify verify-check verify-fast eval

help: ## 显示可用命令
	@echo "make dev          启动 API + Chat + Workspace（自动准备 .env、数据库、依赖）"
	@echo "make dev-stop     停止本地 3000/8000 监听进程"
	@echo "make dev-reset    重建本地开发库（停服务、迁移、重播种；需确认）"
	@echo "make status       查看端口/数据库/迁移/模型/契约状态"
	@echo "make verify       全量验证并写回 CURRENT"
	@echo "make verify-check 全量验证，不写 CURRENT（保留退出码）"
	@echo "make verify-fast  后端快速检查"
	@echo "make eval         场景评测"

dev: ## 启动本地开发环境
	./scripts/dev.sh

dev-reset: ## 重建本地开发库；非交互用 ARGS=--yes
	UV_CACHE_DIR=$${UV_CACHE_DIR:-./.uv-cache} uv run python scripts/reset_dev_db.py $(ARGS)

verify: ## 全量验证并写回 CURRENT
	./scripts/verify.sh

verify-check: ## 全量验证，不写回 CURRENT；保留退出码
	@log=$$(mktemp); \
	trap 'rm -f "$$log"' EXIT; \
	if ./scripts/verify.sh --no-record >"$$log" 2>&1; then \
	  tail -5 "$$log"; \
	else \
	  tail -40 "$$log"; exit 1; \
	fi

verify-fast: ## 后端快速检查
	./scripts/verify.sh --fast

eval: ## 场景评测
	./scripts/eval.sh
