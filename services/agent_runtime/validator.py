"""结果文案校验：唯一模板之外一律替换（AC-10、AC-11、AC-16）。"""

from dataclasses import dataclass

from services.api.domain.cancellation import CancellationState, CancelReason, render_result

MISMATCH = "REPLY_MISMATCH"


@dataclass(frozen=True)
class ValidatedReply:
    reply: str
    replaced: bool
    mismatch: str | None = None


def validate_reply(
    state: CancellationState,
    reason_code: CancelReason | str | None,
    draft: str,
) -> ValidatedReply:
    """把草稿对照唯一模板；不一致时返回模板，不保留草稿措辞。"""
    expected = render_result(state, reason_code).reply
    if draft.strip() == expected:
        return ValidatedReply(reply=expected, replaced=False)
    return ValidatedReply(reply=expected, replaced=True, mismatch=MISMATCH)
