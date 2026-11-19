"""跨层身份值对象（不依赖 FastAPI）。

认证与会话实现分别在 `backend/identity/customer_sessions.py` 与
`backend/identity/employee_sessions.py`；本模块只保留旧取消工作流与
Tool/Workflow 层仍在使用的 `Identity` 类型。
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class Identity:
    account_id: str
    user_id: str
    tenant_id: str
    display_name: str
    tenant_name: str
