"""运行期配置。默认按 production 运行；本机开发需在 .env 设置 ENVIRONMENT=development。"""

from pydantic_settings import BaseSettings, SettingsConfigDict

TEST_ENVIRONMENTS = {"development", "test"}


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql+asyncpg://ba@127.0.0.1:5432/customer_service"
    environment: str = "production"

    @property
    def test_accounts_enabled(self) -> bool:
        """只有明确的开发/测试环境才启用测试账号，其余值一律关闭。"""
        return self.environment in TEST_ENVIRONMENTS

    confirm_timeout_minutes: int = 30
    model_base_url: str = "https://api.openai.com/v1"
    model_name: str = "gpt-4o-mini"
    model_api_key: str = ""
    oms_timeout_seconds: float = 2.0
    max_retries: int = 3


settings = Settings()
