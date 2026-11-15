"""会话接口：建立、查询与退出。"""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, ConfigDict

from services.api.auth import (
    SESSION_COOKIE,
    SESSION_TTL,
    Identity,
    create_session,
    current_identity,
    destroy_session,
)

router = APIRouter()


class SessionRequest(BaseModel):
    """只接受 account_id；租户与用户不得由请求体提供。"""

    model_config = ConfigDict(extra="forbid")

    account_id: str


def _public(identity: Identity) -> dict[str, str]:
    return {
        "account_id": identity.account_id,
        "user_id": identity.user_id,
        "tenant_id": identity.tenant_id,
        "display_name": identity.display_name,
    }


@router.post("/session")
def login(payload: SessionRequest, request: Request, response: Response) -> dict[str, str]:
    result = create_session(payload.account_id)
    if result is None:
        raise HTTPException(status_code=404, detail="账号不存在")
    sid, identity = result
    # 切换账号时结束旧会话，避免旧 sid 继续可用
    destroy_session(request.cookies.get(SESSION_COOKIE))
    response.set_cookie(
        SESSION_COOKIE,
        sid,
        httponly=True,
        samesite="lax",
        max_age=int(SESSION_TTL.total_seconds()),
    )
    return _public(identity)


@router.get("/session")
def whoami(identity: Annotated[Identity, Depends(current_identity)]) -> dict[str, str]:
    return _public(identity)


@router.delete("/session", status_code=204)
def logout(request: Request, response: Response) -> None:
    destroy_session(request.cookies.get(SESSION_COOKIE))
    response.delete_cookie(SESSION_COOKIE)
