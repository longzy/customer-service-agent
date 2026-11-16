.DEFAULT_GOAL := help

.PHONY: help dev verify verify-fast eval

help: ## 显示可用命令
	@echo "make dev          启动 API + Web（自动准备 .env、数据库、依赖）"
	@echo "make verify       全量验证"
	@echo "make verify-fast  后端快速检查"
	@echo "make eval         场景评测"

dev: ## 启动本地开发环境
	./scripts/dev.sh

verify: ## 全量验证
	./scripts/verify.sh

verify-fast: ## 后端快速检查
	./scripts/verify.sh --fast

eval: ## 场景评测
	./scripts/eval.sh
