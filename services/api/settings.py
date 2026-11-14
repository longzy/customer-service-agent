"""运行期配置。默认值对应本机开发环境，部署时必须通过环境变量覆盖。"""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql+asyncpg://ba@127.0.0.1:5432/customer_service"
    confirm_timeout_minutes: int = 30
    oms_timeout_seconds: float = 2.0
    max_retries: int = 3


settings = Settings()
