"""运行期配置。默认按 production 运行；本机开发需在 .env 设置 ENVIRONMENT=development。"""

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

TEST_ENVIRONMENTS = {"development", "test"}
# 本地开发默认的前端地址：Next 开发服务器通过 /api 反向代理到后端
DEV_FRONTEND_ORIGINS = frozenset({"http://localhost:3000", "http://127.0.0.1:3000"})


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql+asyncpg://ba@127.0.0.1:5432/customer_service"
    environment: str = "production"
    # Cookie 是否带 Secure；为空时按环境推导，显式设置可覆盖
    cookie_secure: bool | None = None
    # 额外允许的跨站写请求来源，逗号分隔；默认只允许同源
    allowed_origins: str = ""

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
    model_base_url: str = "https://api.openai.com/v1"
    model_name: str = "gpt-4o-mini"
    model_api_key: str = ""
    oms_timeout_seconds: float = 2.0
    max_retries: int = 3
    retry_backoff_seconds: float = 1.0


settings = Settings()
