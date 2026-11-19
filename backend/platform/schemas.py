"""HTTP 契约共享类型：所有业务域共用的错误封套。"""

from pydantic import BaseModel, ConfigDict


class ErrorEnvelope(BaseModel):
    """所有新 M1 API 的错误封套。"""

    model_config = ConfigDict(extra="forbid")

    code: str
    retryable: bool
    visible: bool
    message: str
