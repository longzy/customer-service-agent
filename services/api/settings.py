"""运行期配置。默认值对应本机开发环境，部署时必须通过环境变量覆盖。"""

from pydantic_settings import BaseSettings, SettingsConfigDict

TEST_ENVIRONMENTS = {"development", "test"}


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql+asyncpg://ba@127.0.0.1:5432/customer_service"
    environment: str = "development"

    @property
    def test_accounts_enabled(self) -> bool:
        """只有明确的开发/测试环境才启用测试账号，其余值一律关闭。"""
        return self.environment in TEST_ENVIRONMENTS

    confirm_timeout_minutes: int = 30
    oms_timeout_seconds: float = 2.0
    max_retries: int = 3


settings = Settings()
