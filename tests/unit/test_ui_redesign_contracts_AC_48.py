"""002 UI 改版的响应式契约：断点、横向滚动与窄屏只读。

2026-11-20 v5 主题重设计后同步：客户侧深色品牌栏改为顶栏与浅色登录品牌区，
工作台侧栏 208/232，队列表格 768 以下收敛为只读三列（原因/末条/操作隐藏）。
"""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def _read(relative: str) -> str:
    return (ROOT / relative).read_text(encoding="utf-8")


def test_breakpoints_and_horizontal_scroll_AC_48() -> None:
    """关键断点成对存在；队列表格横向滚动，不压缩列宽。"""
    chat_login = _read("apps/chat/features/auth/components/LoginBrand.tsx")
    chat_chat = _read("apps/chat/features/chat/components/MessageList.tsx")
    chat_shell = _read("apps/chat/features/chat/components/ChatShell.tsx")
    queue_table = _read("apps/workspace/features/queue/components/QueueTable.tsx")
    queue_nav = _read("apps/workspace/features/queue/components/WorkspaceNav.tsx")
    detail = _read("apps/workspace/features/queue/components/DetailPanel.tsx")

    assert "max-[1023px]:flex-row" in chat_login
    assert "max-w-[560px]" in chat_chat
    assert "max-[767px]:sticky" in chat_shell
    assert "overflow-auto" in queue_table
    assert "min-w-[760px]" in queue_table
    assert "max-[767px]:hidden" in queue_table
    assert "max-[1279px]:w-[208px]" in queue_nav
    assert "请使用桌面端领取会话" in detail
