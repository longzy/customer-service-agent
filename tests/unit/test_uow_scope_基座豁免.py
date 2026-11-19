"""请求级 UoW：提交失败必须回滚，且所有注入点使用 function scope。"""

import re
from pathlib import Path

import pytest
from sqlalchemy.exc import SQLAlchemyError

from backend.platform.db import get_read_session, get_session

BACKEND = Path(__file__).resolve().parents[2] / "backend"
DEPENDS_CALL = re.compile(r"Depends\(\s*get_(?:read_)?session[^)]*\)")


async def test_commit失败回滚并抛出_基座豁免(monkeypatch: pytest.MonkeyPatch) -> None:
    generator = get_session()
    session = await anext(generator)
    calls: list[str] = []

    async def fail_commit() -> None:
        raise SQLAlchemyError("commit boom")

    async def rollback() -> None:
        calls.append("rollback")

    monkeypatch.setattr(session, "commit", fail_commit)
    monkeypatch.setattr(session, "rollback", rollback)

    with pytest.raises(SQLAlchemyError):
        await anext(generator)

    assert calls == ["rollback"]


async def test_read_session关闭不提交_基座豁免(monkeypatch: pytest.MonkeyPatch) -> None:
    generator = get_read_session()
    session = await anext(generator)
    calls: list[str] = []

    async def record_commit() -> None:
        calls.append("commit")

    monkeypatch.setattr(session, "commit", record_commit)
    with pytest.raises(StopAsyncIteration):
        await anext(generator)

    assert calls == []


def test_所有get_session注入都是function_scope_基座豁免() -> None:
    offenders: list[str] = []
    for path in sorted(BACKEND.rglob("*.py")):
        text = path.read_text(encoding="utf-8")
        for call in DEPENDS_CALL.findall(text):
            if 'scope="function"' not in call:
                offenders.append(f"{path}: {call}")

    assert offenders == [], f'以下注入缺少 scope="function"：{offenders}'
