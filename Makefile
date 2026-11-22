.DEFAULT_GOAL := help

.PHONY: help dev dev-stop dev-reset status verify verify-check verify-changed verify-fast review-check review-pack eval lint typecheck test test-reuse gen-contracts gen-tasks dashboard

help: ## 显示可用命令
	@echo "make dev          启动 API + Chat + Workspace（自动准备 .env、数据库、依赖）"
	@echo "                  ARGS 透传参数，如 make dev ARGS=--no-install"
	@echo "make dev-stop     停止本地 3000/3001/8000 监听进程"
	@echo "make dev-reset    重建本地开发库（停服务、迁移、重播种；需确认）"
	@echo "make status       查看端口/数据库/迁移/模型/契约状态"
	@echo "make verify       全量验证并写回 CURRENT（代码未变时复用慢检查）"
	@echo "make verify-check 全量验证，不写 CURRENT（保留退出码）"
	@echo "make verify-changed 按变更范围验证（实现内环，ARGS=F-08）"
	@echo "make verify-fast  后端快速检查"
	@echo "make review-check 评审前置快检（机械/文档/状态/契约）"
	@echo "make review-pack  生成两轴评审包（ARGS=\"F-08\"）"
	@echo "make eval         场景评测"
	@echo "make lint         ruff check + format check"
	@echo "make typecheck    mypy backend"
	@echo "make test         pytest（独立测试库）"
	@echo "make test-reuse   复用固定测试库跑 pytest（迭代用；ARGS 透传）"
	@echo "make gen-contracts 重新生成契约、前端类型与测试快照"
	@echo "make gen-tasks    从执行卡 frontmatter 生成 tasks.md"
	@echo "make dashboard    生成 docs/dashboard.html 与 status.json"

dev: ## 启动本地开发环境；非交互可 ARGS=--no-install
	./scripts/dev.sh $(ARGS)

dev-stop: ## 停止本地 3000/3001/8000 监听进程
	./scripts/dev-stop.sh

status: ## 查看端口/数据库/迁移/模型/契约状态
	./scripts/status.sh

dev-reset: ## 重建本地开发库；非交互用 ARGS=--yes
	UV_CACHE_DIR=$${UV_CACHE_DIR:-./.uv-cache} uv run python scripts/reset_dev_db.py $(ARGS)

verify: gen-tasks dashboard ## 全量验证并写回 CURRENT（先生成派生物）
	./scripts/verify.sh --reuse

verify-check: gen-tasks dashboard ## 全量验证，不写回 CURRENT；保留退出码
	@log=$$(mktemp); \
	trap 'rm -f "$$log"' EXIT; \
	if ./scripts/verify.sh --no-record >"$$log" 2>&1; then \
	  tail -5 "$$log"; \
	else \
	  tail -40 "$$log"; exit 1; \
	fi

verify-changed: ## 按变更范围验证；实现内环
	./scripts/verify-changed.sh $(ARGS)

verify-fast: ## 后端快速检查
	./scripts/verify.sh --fast

review-check: ## 评审前置快检
	./scripts/review-check.sh

review-pack: ## 生成评审包
	UV_CACHE_DIR=$${UV_CACHE_DIR:-./.uv-cache} uv run python scripts/review_pack.py $(ARGS)

eval: ## 场景评测
	./scripts/eval.sh

lint: ## ruff check + format check
	UV_CACHE_DIR=$${UV_CACHE_DIR:-./.uv-cache} uv run ruff check .
	UV_CACHE_DIR=$${UV_CACHE_DIR:-./.uv-cache} uv run ruff format --check .

typecheck: ## mypy backend
	UV_CACHE_DIR=$${UV_CACHE_DIR:-./.uv-cache} uv run mypy backend

test: ## pytest（独立测试库）
	./scripts/test-db.sh -q

test-reuse: ## 复用固定测试库跑 pytest（迭代用）
	TEST_DB_NAME=customer_service_test_dev ./scripts/test-db.sh $(ARGS)

gen-contracts: ## 重新生成契约、前端类型与测试快照
	./scripts/gen-contracts.sh

gen-tasks: ## 从执行卡 frontmatter 生成 tasks.md
	./.venv/bin/python scripts/gen_tasks.py

dashboard: ## 生成项目驾驶舱
	./.venv/bin/python scripts/gen_board.py
