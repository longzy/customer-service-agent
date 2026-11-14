#!/usr/bin/env python3
"""文档一致性检查。

用法：
    python3 scripts/check-docs.py

检查项：
1. Markdown 内部链接是否都能解析。
2. 文档状态词是否在允许集合内。
3. docs/CURRENT.md 是否包含协作规范第 5 节要求的全部字段。
4. acceptance.md 中每条 AC 是否被 tasks.md 引用。
5. 设计卡标记为"待开工许可"或"已确认"时，其依据文档必须已批准。

退出码：0 全部通过；1 存在错误。
"""

import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SPECS_DIR = os.path.join(ROOT, "docs", "specs")

STATUS_WORDS = {
    "未开始", "草案", "拟议", "等待评审", "已批准",
    "进行中", "阻塞", "已完成", "已暂停",
    "已关闭", "已清零", "待确认", "待开工许可",
}

CURRENT_REQUIRED_FIELDS = [
    "更新日期", "项目阶段", "当前状态", "当前 Milestone",
    "最近验证", "已完成", "进行中", "阻塞", "下一步", "待确认决策",
]

GATE_OPEN_STATUSES = ("待开工许可", "已确认")

errors = []
checked = {"links": 0, "files": 0, "acs": 0, "cards": 0}


def rel(path):
    return os.path.relpath(path, ROOT)


def md_files():
    for base, dirs, names in os.walk(ROOT):
        dirs[:] = [d for d in dirs if d != ".git"]
        for name in names:
            if name.endswith(".md"):
                yield os.path.join(base, name)


def read(path):
    with open(path, encoding="utf-8") as handle:
        return handle.read()


def check_links(files):
    pattern = re.compile(r"\[[^\]]*\]\(([^)#]+?)(?:#[^)]*)?\)")
    for path in files:
        for target in pattern.findall(read(path)):
            if target.startswith(("http", "mailto:")):
                continue
            checked["links"] += 1
            resolved = os.path.normpath(os.path.join(os.path.dirname(path), target))
            if not os.path.exists(resolved):
                errors.append("%s：链接目标不存在 %s" % (rel(path), target))


def check_status_words(files):
    """只检查文件头部（前 15 行）的文档状态，避免与组件状态清单混淆。"""
    status = re.compile(r"^- 状态：(.+)$", re.M)
    for path in files:
        header = "\n".join(read(path).splitlines()[:15])
        for value in status.findall(header):
            token = re.split(r"[（(，,、\s]", value.strip())[0]
            if token and token not in STATUS_WORDS:
                errors.append("%s：状态词不在允许集合内：%s" % (rel(path), token))


def check_current_fields():
    path = os.path.join(ROOT, "docs", "CURRENT.md")
    text = read(path)
    for field in CURRENT_REQUIRED_FIELDS:
        if field not in text:
            errors.append("docs/CURRENT.md：缺少规范第 5 节要求的字段 %s" % field)


def check_ac_coverage():
    acceptance = os.path.join(SPECS_DIR, "M1-order-cancel", "acceptance.md")
    tasks = os.path.join(SPECS_DIR, "M1-order-cancel", "tasks.md")
    if not (os.path.exists(acceptance) and os.path.exists(tasks)):
        return
    acs = sorted(set(re.findall(r"\bAC-\d{2}\b", read(acceptance))))
    tasks_text = read(tasks)
    checked["acs"] = len(acs)
    for ac in acs:
        if ac not in tasks_text:
            errors.append("docs/specs/M1-order-cancel/tasks.md：缺少对 %s 的引用" % ac)


def doc_status(path):
    match = re.search(r"^- 状态：(.+)$", read(path), re.M)
    return match.group(1).strip() if match else ""


def resolve_reference(card_path, ref):
    """依次在仓库根、设计卡所在目录及其各级上级目录中解析相对引用。"""
    candidates = [os.path.join(ROOT, ref)]
    directory = os.path.dirname(card_path)
    while True:
        candidates.append(os.path.join(directory, ref))
        parent = os.path.dirname(directory)
        if directory == ROOT or parent == directory:
            break
        directory = parent
    for candidate in candidates:
        if os.path.exists(candidate):
            return os.path.normpath(candidate)
    return None


def check_design_card_gate():
    cards = [p for p in md_files() if os.sep + "design-cards" + os.sep in p]
    for card in cards:
        status = doc_status(card)
        if not status.startswith(GATE_OPEN_STATUSES):
            continue
        checked["cards"] += 1
        for line in read(card).splitlines():
            if not line.startswith("- 依据："):
                continue
            for ref in re.findall(r"`([^`]+\.md)`", line):
                target = resolve_reference(card, ref)
                if target is None:
                    errors.append("%s：依据文档不存在 %s" % (rel(card), ref))
                    continue
                if not doc_status(target).startswith(("已批准", "已清零")):
                    errors.append(
                        "%s：状态为 %s，但依据文档 %s 尚未批准"
                        % (rel(card), status, rel(target))
                    )


def main():
    files = sorted(md_files())
    checked["files"] = len(files)
    check_links(files)
    check_status_words(files)
    check_current_fields()
    check_ac_coverage()
    check_design_card_gate()

    if errors:
        print("文档检查失败，%d 个问题：" % len(errors))
        for item in errors:
            print("  - " + item)
        return 1

    print(
        "文档检查通过：%d 个文件、%d 条链接、%d 条 AC、%d 张设计卡。"
        % (checked["files"], checked["links"], checked["acs"], checked["cards"])
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
