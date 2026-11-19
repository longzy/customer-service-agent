"""运行期配置。默认按 production 运行；本机开发需在 .env 设置 ENVIRONMENT=development。"""

import os

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

TEST_ENVIRONMENTS = {"development", "test"}
# 本地开发默认的前端地址：Next 开发服务器通过 /api 反向代理到后端
DEV_FRONTEND_ORIGINS = frozenset(
    {
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "http://localhost:3001",
        "http://127.0.0.1:3001",
    }
)


class Settings(BaseSettings):
    # SETTINGS_ENV_FILE 让测试可以关掉 .env（test-db.sh 传 /dev/null），
    # 避免本地绿、CI 红的配置漂移。
    model_config = SettingsConfigDict(
        env_file=os.environ.get("SETTINGS_ENV_FILE", ".env"), extra="ignore"
    )

    database_url: str = "postgresql+asyncpg://ba@127.0.0.1:5432/customer_service"
    # 业务连接池；每个 worker 独立。上限 = size + max_overflow。
    db_pool_size: int = 5
    db_max_overflow: int = 10
    db_pool_timeout: float = 30.0
    db_pool_recycle: int = 1800
    # Trace 独立小池：只写 tool_executions，满了快速失败，不抢业务连接。
    trace_pool_size: int = 2
    trace_max_overflow: int = 2
    trace_pool_timeout: float = 2.0
    # 技术 trace 正常成功的采样率；错误/关键工具始终 100%。
    trace_sample_rate: float = 0.05
    # 技术 trace 有界缓冲与批量写：满了丢最旧，不阻断业务。
    trace_buffer_size: int = 1000
    trace_flush_interval_ms: int = 2000
    trace_batch_size: int = 200
    environment: str = "production"
    # Cookie 是否带 Secure；为空时按环境推导，显式设置可覆盖
    cookie_secure: bool | None = None
    # 额外允许的跨站写请求来源，逗号分隔；默认只允许同源
    allowed_origins: str = ""

    @field_validator("trace_sample_rate")
    @classmethod
    def _sample_rate_in_range(cls, value: float) -> float:
        if not 0.0 <= value <= 1.0:
            raise ValueError("TRACE_SAMPLE_RATE 必须在 0..1 之间")
        return value

    @field_validator("cookie_secure", mode="before")
    @classmethod
    def _empty_means_auto(cls, value: object) -> object:
        """`COOKIE_SECURE=` 这类空值按“未设置”处理，避免照抄示例就启动失败。"""
        if isinstance(value, str) and not value.strip():
            return None
        return value

    @property
    def test_accounts_enabled(self) -> bool:
        """只有明确的开发/测试环境才启用测试账号，其余值一律关闭。"""
        return self.environment in TEST_ENVIRONMENTS

    @property
    def secure_cookie(self) -> bool:
        """非开发/测试环境默认要求 Secure；COOKIE_SECURE 可显式覆盖。"""
        if self.cookie_secure is not None:
            return self.cookie_secure
        return self.environment not in TEST_ENVIRONMENTS

    @property
    def allowed_origin_set(self) -> set[str]:
        """把逗号分隔的白名单解析为集合；开发/测试环境加入本地前端地址。"""
        items = {item.strip() for item in self.allowed_origins.split(",") if item.strip()}
        if self.environment in TEST_ENVIRONMENTS:
            items |= DEV_FRONTEND_ORIGINS
        return items

    confirm_timeout_minutes: int = 30
    # M1 新路由总开关：回滚时置 false，M1-P 旧路由保持可用
    m1_enabled: bool = True
    # M1 单租户部署；登录按该租户解析客户账号
    m1_tenant_id: str = "tenant-a"
    # 演示账号密码只从 .env 读取，不提交；种子脚本缺失时失败
    demo_password: str = ""
    # 客户聊天模型单次调用上限；plan 3.3.4 固定 10s，测试可注入更短值
    customer_model_timeout_seconds: float = 10.0
    # 仅开发/测试的假模型行为：none / error / timeout，用于人工演示失败路径
    fake_model_mode: str = "none"
    model_base_url: str = "https://api.openai.com/v1"
    model_name: str = "gpt-4o-mini"
    model_api_key: str = ""
    oms_base_url: str = ""
    oms_timeout_seconds: float = 2.0
    max_retries: int = 3
    retry_backoff_seconds: float = 1.0


settings = Settings()
