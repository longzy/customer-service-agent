"""Spec/计划门禁：批准状态、T3 设计章节、DoR 与触点/判定表/回滚。"""

import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "check-spec.py"


def load_module():
    spec = importlib.util.spec_from_file_location("check_spec", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def write_repo(root: Path, *, status: str = "已批准", t3: bool = True, dor: bool = True) -> None:
    spec = root / "docs" / "specs" / "009-demo"
    card = root / "docs" / "tasks" / "009-demo"
    spec.mkdir(parents=True)
    card.mkdir(parents=True)
    risk = "T3" if t3 else "T2"
    (spec / "requirements.md").write_text(
        f"# demo\n\n- 状态：{status}\n- 风险级别：{risk}\n\n"
        "## 1. 客户新闻稿\n\n非目标：不做退款\n\n"
        "## 附录 A. 验收标准（AC）\n\n| AC | 角色 | 场景 | 期望 |\n|---|---|---|---|\n"
        "| AC-99 | 客户 | demo | demo |\n",
        encoding="utf-8",
    )
    security = "威胁\n越权矩阵\n回滚\n" if t3 else ""
    (spec / "design.md").write_text(
        f"# demo design\n\n- 状态：{status}\n- 规模：{risk}\n\n"
        "## 1. 背景与范围\n\n## 2. 目标与非目标\n\n## 3. 方案\n\n"
        "## 4. 备选方案\n\n## 5. 跨切面关注点\n\n## 6. 未决问题\n\n"
        f"{security}",
        encoding="utf-8",
    )
    checkbox = "[x]" if dor else "[ ]"
    (card / "F-99.md").write_text(
        "---\nid: F-99\ntitle: demo\nspec: 009-demo\nmilestone: M1\n"
        "status: review\ncategory: functional\nac: [AC-99]\n"
        f"risk: {risk}\nupdated: 2026-11-22\n---\n\n"
        "# 任务执行卡：F-99 demo\n\n"
        "### 1.1 触点（文件 → 改什么）\n\n| 文件 | 改动 |\n|---|---|\n| a | b |\n\n"
        "### 2.1 前置条件（Definition of Ready）\n\n"
        f"- {checkbox} 依赖已完成\n- {checkbox} 规格已批准\n- {checkbox} seam 可用\n"
        f"- {checkbox} 无待决问题\n- {checkbox} 迁移就绪\n\n"
        "### 2.5 判定表与失败矩阵\n\n| AC | 主路径 |\n|---|---|\n| AC-99 | demo |\n\n"
        "## 7. 发布与回滚（T2/T3 必填，T1 可省）\n\n- 回滚：降级\n",
        encoding="utf-8",
    )


def test_完整规格与执行卡通过_基座豁免(tmp_path: Path, capsys) -> None:
    write_repo(tmp_path)
    assert load_module().main(["--root", str(tmp_path)]) == 0
    assert "Spec/计划门禁通过" in capsys.readouterr().out


def test_未批准规格阻断_基座豁免(tmp_path: Path, capsys) -> None:
    write_repo(tmp_path, status="草案")
    assert load_module().main(["--root", str(tmp_path)]) == 1
    assert "必须为「已批准」" in capsys.readouterr().err


def test_T3设计缺威胁模型阻断_基座豁免(tmp_path: Path, capsys) -> None:
    write_repo(tmp_path, t3=True)
    design = tmp_path / "docs" / "specs" / "009-demo" / "design.md"
    design.write_text(design.read_text(encoding="utf-8").replace("威胁\n", ""), encoding="utf-8")
    assert load_module().main(["--root", str(tmp_path)]) == 1
    assert "T3 设计缺少" in capsys.readouterr().err


def test_DoR未勾选阻断_基座豁免(tmp_path: Path, capsys) -> None:
    write_repo(tmp_path, dor=False)
    assert load_module().main(["--root", str(tmp_path)]) == 1
    assert "DoR 未全部满足" in capsys.readouterr().err


def test_旧模型无risk卡跳过_基座豁免(tmp_path: Path, capsys) -> None:
    write_repo(tmp_path)
    card = tmp_path / "docs" / "tasks" / "009-demo" / "F-99.md"
    card.write_text(card.read_text(encoding="utf-8").replace("risk: T3\n", ""), encoding="utf-8")
    assert load_module().main(["--root", str(tmp_path)]) == 0
    assert "Spec/计划门禁通过" in capsys.readouterr().out
