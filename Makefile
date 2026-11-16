.DEFAULT_GOAL := help

.PHONY: help dev dev-no-install verify verify-fast eval

help: ## 显示可用命令
	@echo "make dev            启动 API + Web（自动准备 .env、数据库、依赖）"
	@echo "make dev-no-install 跳过依赖安装，重复启动"
	@echo "make verify         全量验证"
	@echo "make verify-fast    后端快速检查"
	@echo "make eval           场景评测"

dev: ## 启动本地开发环境
	./scripts/dev.sh

dev-no-install: ## 启动本地开发环境，跳过依赖安装
	./scripts/dev.sh --no-install

verify: ## 全量验证
	./scripts/verify.sh

verify-fast: ## 后端快速检查
	./scripts/verify.sh --fast

eval: ## 场景评测
	./scripts/eval.sh
