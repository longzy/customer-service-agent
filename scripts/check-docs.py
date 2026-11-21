#!/usr/bin/env python3
"""文档一致性与 Spec 结构检查。

用法：
    python3 scripts/check-docs.py

检查项见 docs/process/WORKFLOW.md 第 3、4 节。
退出码：0 全部通过；1 存在错误。
"""

import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SPECS_ROOT = os.path.join(ROOT, "docs", "specs")
TASKS_ROOT = os.path.join(ROOT, "docs", "tasks")
REVIEWS_ROOT = os.path.join(ROOT, "docs", "reviews")
TESTS_ROOT = os.path.join(ROOT, "tests")

SKIP_DIRS = {
    ".git",
    ".venv",
    "node_modules",
    ".next",
    ".uv-cache",
    ".pnpm-store",
    ".workbuddy",
    "coverage",
    "mutants",
    ".mutmut-cache",
}

STATUS_WORDS = {
    "未开始",
    "草案",
    "拟议",
    "等待评审",
    "已批准",
    "进行中",
    "阻塞",
    "已完成",
    "已暂停",
    "已关闭",
    "已清零",
    "待确认",
    "已确认",
    "待开工许可",
    "待评审",
}

# 上下文预算：超过即失败，防止规则与状态重新膨胀
CONTEXT_BUDGETS = {
    "AGENTS.md": 60,
    "docs/STATUS.md": 80,
    "docs/process/WORKFLOW.md": 200,
    "docs/process/standards.md": 60,
}

CURRENT_REQUIRED_FIELDS = [
    "更新日期",
    "项目阶段",
    "当前状态",
    "当前 Milestone",
    "最近验证",
    "已完成",
    "进行中",
    "阻塞",
    "下一步",
    "待确认决策",
]

SPEC_LAYOUTS = ({"brief": "requirements.md", "plan": "design.md", "features": "tasks.md"},)

GATE_OPEN_STATUSES = ("待开工许可", "已确认")
REVIEW_REQUIRED = ("## 0. 门禁复核", "## 逐 AC", "## 阻断项", "## 结论")
SPEC_DIR_PATTERN = re.compile(r"^\d{3}-[a-z0-9-]+$")
CARD_PATTERN = re.compile(r"^[TF]-\d{2}\.md$")
# AC 只认 brief 的验收表格行；正文里引用其他 spec 的 AC 不参与覆盖检查。
AC_ROW_PATTERN = re.compile(r"^\|\s*(AC-\d{2})\s*\|", re.M)
# CURRENT 验证块之外不得手写验证计数：唯一事实源是 verify.sh 生成的块。
PASS_COUNT_PATTERN = re.compile(r"\b\d+ passed\b")

TEST_DEF_PATTERN = re.compile(r"^\s*(?:async\s+)?def\s+(test_[^\s(]+)", re.M)
TEST_REF_PATTERN = re.compile(r"`(test_[^`\s]+)`")

errors = []
checked = {
    "links": 0,
    "files": 0,
    "acs": 0,
    "cards": 0,
    "specs": 0,
    "skipped": 0,
    "reviews": 0,
    "test_refs": 0,
}


def rel(path):
    return os.path.relpath(path, ROOT)


def md_files():
    for base, dirs, names in os.walk(ROOT):
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
        for name in names:
            if name.endswith(".md"):
                yield os.path.join(base, name)


def read(path):
    with open(path, encoding="utf-8") as handle:
        return handle.read()


FRONTMATTER_STATUS = {
    "done": "已完成",
    "doing": "进行中",
    "review": "待评审",
    "todo": "未开始",
    "blocked": "阻塞",
}


def doc_status(path):
    text = read(path)
    front = re.match(r"^---\n(.*?)\n---\n", text, re.S)
    if front:
        for line in front.group(1).splitlines():
            key, sep, value = line.partition(":")
            if sep and key.strip() == "status":
                value = value.strip()
                return FRONTMATTER_STATUS.get(value, value)
    header = "\n".join(text.splitlines()[:15])
    match = re.search(r"^- 状态：(.+)$", header, re.M)
    return match.group(1).strip() if match else ""


def check_links(files):
    pattern = re.compile(r"\[[^\]]*\]\(([^)#]+?)(?:#[^)]*)?\)")
    for path in files:
        for target in pattern.findall(read(path)):
            if target.startswith(("http", "mailto:")):
                continue
            checked["links"] += 1
            resolved = os.path.normpath(os.path.join(os.path.dirname(path), target))
            if not os.path.exists(resolved):
                errors.append(f"{rel(path)}：链接目标不存在 {target}")


def check_status_words(files):
    """只检查文件头部的文档状态，避免与组件状态清单混淆。"""
    status = re.compile(r"^- 状态：(.+)$", re.M)
    for path in files:
        header = "\n".join(read(path).splitlines()[:15])
        for value in status.findall(header):
            token = re.split(r"[（(，,、\s]", value.strip())[0]
            if token and token not in STATUS_WORDS:
                errors.append(f"{rel(path)}：状态词不在允许集合内：{token}")


def check_current_fields():
    text = read(os.path.join(ROOT, "docs", "STATUS.md"))
    for field in CURRENT_REQUIRED_FIELDS:
        if field not in text:
            errors.append(f"docs/STATUS.md：缺少规范第 5 节要求的字段 {field}")


def spec_dirs():
    """返回 (规格目录名, 绝对路径)，并校验命名与编号唯一。"""
    found = []
    if not os.path.isdir(SPECS_ROOT):
        return found
    numbers = {}
    for name in sorted(os.listdir(SPECS_ROOT)):
        path = os.path.join(SPECS_ROOT, name)
        if not os.path.isdir(path):
            continue
        if not SPEC_DIR_PATTERN.match(name):
            errors.append(f"{rel(path)}：规格目录名不符合 NNN-slug 约定")
            continue
        number = name.split("-")[0]
        if number in numbers:
            errors.append(f"规格编号 {number} 重复（{numbers[number]} 与 {name}）")
        numbers[number] = name
        found.append((name, path))
    return found


def spec_layout(path):
    """返回完整布局；若有部分文件，返回最接近布局及缺失项。"""
    partial = None
    for layout in SPEC_LAYOUTS:
        present = [value for value in layout.values() if os.path.exists(os.path.join(path, value))]
        if len(present) == len(layout):
            return layout, []
        if present and partial is None:
            missing = [value for value in layout.values() if value not in present]
            partial = (layout, missing)
    return partial if partial else (None, [])


def check_spec_structure(specs):
    for name, path in specs:
        checked["specs"] += 1
        layout, missing = spec_layout(path)
        if layout is None:
            errors.append(f"docs/specs/{name}：缺少完整布局（requirements.md/design.md/tasks.md）")
        elif missing:
            errors.append(f"docs/specs/{name}：缺少 {', '.join(missing)}")


def check_ac_coverage(specs):
    for name, path in specs:
        layout, missing = spec_layout(path)
        if layout is None or missing:
            continue
        brief = os.path.join(path, layout["brief"])
        features = os.path.join(path, layout["features"])
        acs = sorted(set(AC_ROW_PATTERN.findall(read(brief))))
        features_text = read(features)
        checked["acs"] += len(acs)
        for ac in acs:
            if ac not in features_text:
                errors.append(f"docs/specs/{name}/{layout['features']}：缺少对 {ac} 的引用")


def check_task_dirs(specs):
    spec_names = {name for name, _ in specs}
    if not os.path.isdir(TASKS_ROOT):
        return
    for name in sorted(os.listdir(TASKS_ROOT)):
        path = os.path.join(TASKS_ROOT, name)
        if not os.path.isdir(path):
            continue
        if not SPEC_DIR_PATTERN.match(name):
            errors.append(f"{rel(path)}：执行卡目录名不符合 NNN-slug 约定")
            continue
        if name not in spec_names:
            errors.append(f"{rel(path)}：没有同名规格目录 docs/specs/*/{name}")
        for card in sorted(os.listdir(path)):
            if not card.endswith(".md"):
                continue
            if not CARD_PATTERN.match(card):
                errors.append(f"{rel(os.path.join(path, card))}：执行卡命名应为 T-XX.md")


PATH_PREFIXES = ("docs/", "backend/", "packages/", "tests/", "scripts/", "apps/", "migrations/")
PATH_TOKEN = re.compile(r"`([^`\n]+)`")
PLANNED_PATH_MARKER = "（待创建）"


def normalize_path_token(token):
    """去掉文档引用里的 #锚点 与 :行号 后缀，只留下仓库路径。"""
    return re.sub(r":\d+(?:-\d+)?$", "", token.split("#", 1)[0])


def is_planned_path(content, match):
    """反引号路径后紧跟“（待创建）”时跳过存在性校验。"""
    return (
        content[match.end() : match.end() + len(PLANNED_PATH_MARKER) + 2]
        .lstrip()
        .startswith(PLANNED_PATH_MARKER)
    )


def check_card_paths():
    """执行卡里引用的仓库路径必须真实存在；尚未创建的文件用“（待创建）”显式标记。"""
    if not os.path.isdir(TASKS_ROOT):
        return
    for base, _dirs, names in os.walk(TASKS_ROOT):
        for card in sorted(names):
            if not CARD_PATTERN.match(card):
                continue
            card_path = os.path.join(base, card)
            content = read(card_path)
            # 评审记录是评审后产物：执行卡 §5 里指向 docs/reviews/ 的路径
            # 在创建前必然不存在，不能算死链。
            review_start = content.find("## 5. 评审")
            review_end = content.find("## 6.", review_start) if review_start != -1 else -1
            for match in PATH_TOKEN.finditer(content):
                token = match.group(1)
                if not token.startswith(PATH_PREFIXES):
                    continue
                if "<" in token or "*" in token or " " in token:
                    continue
                if is_planned_path(content, match):
                    continue
                if (
                    token.startswith("docs/reviews/")
                    and review_start != -1
                    and match.start() > review_start
                    and (review_end == -1 or match.start() < review_end)
                ):
                    continue
                path = normalize_path_token(token).rstrip("/")
                if not path:
                    continue
                if os.path.exists(os.path.join(ROOT, path)):
                    continue
                errors.append(f"{rel(card_path)}：引用的路径不存在 {token}")


def test_names() -> set[str]:
    """收集 tests/ 下真实存在的测试函数名，供文档引用校验。"""
    names: set[str] = set()
    if not os.path.isdir(TESTS_ROOT):
        return names
    for base, dirs, files in os.walk(TESTS_ROOT):
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
        for name in files:
            if name.endswith(".py"):
                names.update(TEST_DEF_PATTERN.findall(read(os.path.join(base, name))))
    return names


def check_test_references():
    """执行卡与评审记录里反引号包裹的 test_* 必须真实存在。"""
    known = test_names()
    if not known:
        return
    for root in (TASKS_ROOT, REVIEWS_ROOT):
        if not os.path.isdir(root):
            continue
        for base, _dirs, names in os.walk(root):
            for name in sorted(names):
                if not name.endswith(".md"):
                    continue
                path = os.path.join(base, name)
                for match in TEST_REF_PATTERN.finditer(read(path)):
                    reference = match.group(1)
                    if "/" in reference or "::" in reference or reference.endswith(".py"):
                        continue
                    checked["test_refs"] += 1
                    if reference not in known:
                        errors.append(f"{rel(path)}：引用的测试不存在 {reference}")


def check_completed_card_reviews():
    """标记已完成的执行卡必须有评审记录，评审不能只存在于对话里。"""
    if not os.path.isdir(TASKS_ROOT):
        return
    for base, _dirs, names in os.walk(TASKS_ROOT):
        for card in sorted(names):
            if not CARD_PATTERN.match(card):
                continue
            card_path = os.path.join(base, card)
            status = doc_status(card_path)
            if not status.startswith("已完成"):
                continue
            spec_name = os.path.basename(base)
            review = os.path.join(REVIEWS_ROOT, spec_name, card)
            if not os.path.exists(review):
                expected = f"docs/reviews/{spec_name}/{card}"
                errors.append(f"{rel(card_path)}：状态为 {status}，但缺少评审记录 {expected}")
                continue
            if "结论" not in read(review):
                errors.append(f"{rel(review)}：评审记录缺少结论")
                continue
            content = read(card_path)
            if "## 4. 证据" in content:
                evidence = content.split("## 4. 证据", 1)[1].split("\n## ", 1)[0]
                if "```" not in evidence or not any(
                    token in evidence for token in ("passed", "FAILED", "$ ")
                ):
                    errors.append(
                        f"{rel(card_path)}：第 4 节证据缺少真实命令输出（代码块且含 passed/FAILED）"
                    )
            checked["reviews"] += 1


def resolve_reference(card_path, ref):
    """依次在仓库根、执行卡所在目录及其各级上级目录中解析相对引用。"""
    spec_dir = os.path.join(ROOT, "docs", "specs", os.path.basename(os.path.dirname(card_path)))
    candidates = [os.path.join(ROOT, ref), os.path.join(spec_dir, ref)]
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
    if not os.path.isdir(TASKS_ROOT):
        return
    for base, _dirs, names in os.walk(TASKS_ROOT):
        for card in sorted(names):
            if not CARD_PATTERN.match(card):
                continue
            card_path = os.path.join(base, card)
            status = doc_status(card_path)
            if not status.startswith(GATE_OPEN_STATUSES):
                checked["skipped"] += 1
                print(f"跳过执行卡 {rel(card_path)}：状态为 {status or '未声明'}")
                continue
            checked["cards"] += 1
            binding = re.search(r"- 绑定验收：(.+)", read(card_path))
            if binding and len(re.findall(r"AC-\d{2}", binding.group(1))) > 2:
                print(f"警告：{rel(card_path)} 绑定超过 2 个 AC，检查是否需要按行为拆分")
            for line in read(card_path).splitlines():
                if not line.startswith("- 依据："):
                    continue
                for ref in re.findall(r"`([^`]+\.md)`", line):
                    target = resolve_reference(card_path, ref)
                    if target is None:
                        errors.append(f"{rel(card_path)}：依据文档不存在 {ref}")
                        continue
                    if not doc_status(target).startswith(("已批准", "已清零")):
                        errors.append(
                            f"{rel(card_path)}：状态为 {status}，但依据文档 {rel(target)} 尚未批准"
                        )


def check_status_vocabulary_sync():
    """sdd.md 状态词表与检查器常量必须一致，避免新增状态时漏改。"""
    path = os.path.join(ROOT, "docs", "process", "WORKFLOW.md")
    if not os.path.exists(path):
        return
    declared = set()
    for line in read(path).splitlines():
        if "状态" not in line or "→" not in line:
            continue
        declared |= set(re.findall(r"`([^`]+)`", line))
    unknown = declared - STATUS_WORDS
    if unknown:
        errors.append(f"docs/process/WORKFLOW.md：状态词未加入检查器：{sorted(unknown)}")


def missing_review_sections(content):
    """评审记录必须包含的固定小节；只有完成卡才强制。"""
    return [heading for heading in REVIEW_REQUIRED if heading not in content]


def check_review_conclusions():
    """评审结论必须是三种枚举之一，且评审文件不能是孤儿。"""
    if not os.path.isdir(REVIEWS_ROOT):
        return
    for base, _dirs, names in os.walk(REVIEWS_ROOT):
        spec_name = os.path.basename(base)
        if not SPEC_DIR_PATTERN.match(spec_name):
            continue  # 历史评审（如初始架构评审）不受执行卡评审格式约束
        for name in sorted(names):
            if not CARD_PATTERN.match(name):
                continue
            path = os.path.join(base, name)
            content = read(path)
            card = os.path.join(TASKS_ROOT, spec_name, name)
            if not os.path.exists(card):
                errors.append(f"{rel(path)}：没有对应的执行卡 {rel(card)}")
                continue
            # 只有已完成执行卡的评审才强制完整模板；待评审阶段允许草稿。
            if not doc_status(card).startswith("已完成"):
                continue
            missing = missing_review_sections(content)
            if missing:
                errors.append(f"{rel(path)}：缺少评审小节 {', '.join(missing)}")
                if "## 结论" not in content:
                    continue
            tail = content.split("## 结论", 1)[1]
            first = next((line.strip() for line in tail.splitlines() if line.strip()), "")
            if not first.startswith(("通过", "有条件通过", "不通过")):
                errors.append(
                    f"{rel(path)}：结论必须为通过/有条件通过/不通过，当前为「{first[:20]}」"
                )


def check_context_budget():
    """入口、状态与流程文档有行数上限；超限先删内容，不新增副本。"""
    for relative, limit in CONTEXT_BUDGETS.items():
        path = os.path.join(ROOT, relative)
        if not os.path.exists(path):
            continue
        lines = len(read(path).splitlines())
        if lines > limit:
            errors.append(f"{relative}：{lines} 行，超过上下文预算 {limit} 行")


def check_verification_block():
    """STATUS.md 的最近验证必须由 verify.sh 生成，防止手写漂移。"""
    path = os.path.join(ROOT, "docs", "STATUS.md")
    content = read(path)
    if "<!-- verify:start -->" not in content or "<!-- verify:end -->" not in content:
        errors.append("docs/STATUS.md：缺少 verify 标记块（由 scripts/verify.sh 生成）")
        return
    block = content.split("<!-- verify:start -->", 1)[1].split("<!-- verify:end -->", 1)[0]
    if "passed" not in block and "待运行" not in block:
        errors.append("docs/STATUS.md：verify 标记块未包含验证结果")


def check_current_handwritten_counts():
    """CURRENT 的验证计数只能来自 verify.sh；其他位置手写会与验证块漂移。"""
    path = os.path.join(ROOT, "docs", "STATUS.md")
    if not os.path.exists(path):
        return
    content = read(path)
    if "<!-- verify:start -->" in content and "<!-- verify:end -->" in content:
        before, rest = content.split("<!-- verify:start -->", 1)
        _block, after = rest.split("<!-- verify:end -->", 1)
        outside = before + after
    else:
        outside = content
    match = PASS_COUNT_PATTERN.search(outside)
    if match is not None:
        errors.append(
            "docs/STATUS.md：验证计数只能写在 verify 标记块（由 verify.sh 生成），"
            f"发现手写「{match.group(0)}」；请改为“见验证块”"
        )


def main():
    files = sorted(md_files())
    checked["files"] = len(files)
    specs = spec_dirs()

    check_links(files)
    check_status_words(files)
    check_current_fields()
    check_spec_structure(specs)
    check_ac_coverage(specs)
    check_task_dirs(specs)
    check_card_paths()
    check_test_references()
    check_design_card_gate()
    check_completed_card_reviews()
    check_status_vocabulary_sync()
    check_review_conclusions()
    check_context_budget()
    check_verification_block()
    check_current_handwritten_counts()

    if errors:
        print(f"文档检查失败，{len(errors)} 个问题：")
        for item in errors:
            print("  - " + item)
        return 1

    print(
        f"文档检查通过：{checked['files']} 个文件、{checked['links']} 条链接、"
        f"{checked['specs']} 个规格目录、{checked['acs']} 条 AC、"
        f"{checked['cards']} 张执行卡已检查、{checked['skipped']} 张跳过、"
        f"{checked['reviews']} 份评审记录已核对、{checked['test_refs']} 条测试引用已校验。"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
