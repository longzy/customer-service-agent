"""工作台 API 的响应契约：OpenAPI 与前端类型的唯一来源。"""

from pydantic import BaseModel, ConfigDict, Field, field_validator

from backend.api.customer_schemas import ConversationStatus


class EmployeeLoginRequest(BaseModel):
    """只接受用户名/密码；租户与员工 id 只能来自服务端配置与 session。"""

    model_config = ConfigDict(extra="forbid")

    username: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=1, max_length=128)

    @field_validator("username")
    @classmethod
    def _strip_username(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("username 不能为空")
        return value


class EmployeePublic(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    tenant_id: str
    username: str
    display_name: str
    role: str


class EmployeeSessionResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    employee: EmployeePublic
    expires_at: str


class WorkspaceConversationResponse(BaseModel):
    """F-05 只暴露归属门禁后的最小会话信息；完整上下文由 F-08 增量扩展。"""

    model_config = ConfigDict(extra="forbid")

    id: str
    status: ConversationStatus
