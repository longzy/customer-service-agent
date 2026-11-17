"""开发期账号列表：登录页的数据来源，生产环境不挂载。"""

from fastapi import APIRouter

from backend.identity import ACCOUNTS, Identity

router = APIRouter()


def _public(identity: Identity) -> dict[str, str]:
    return {
        "account_id": identity.account_id,
        "display_name": identity.display_name,
        "tenant_id": identity.tenant_id,
        "tenant_name": identity.tenant_name,
    }


@router.get("/accounts")
def list_accounts() -> list[dict[str, str]]:
    return [_public(identity) for identity in ACCOUNTS.values()]
