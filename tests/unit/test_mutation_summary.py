"""按函数汇总突变结果：只统计存活/无测试，按缺口排序。"""

from scripts.mutation_summary import parse, render

SAMPLE = """\
    backend.workflows.cancel.CancellationWorkflow.confirm__mutmut_1: survived
    backend.workflows.cancel.CancellationWorkflow.confirm__mutmut_2: killed
    backend.workflows.cancel.xǁSqlCancellationRepositoryǁcreate__mutmut_3: no tests
    backend.domain.cancellation.render_result__mutmut_4: survived
"""


def test_按函数聚合存活与无测试_基座豁免() -> None:
    grouped = parse(SAMPLE)
    confirm = grouped[
        ("backend.workflows.cancel", "backend.workflows.cancel.CancellationWorkflow.confirm")
    ]
    create = grouped[
        (
            "backend.workflows.cancel",
            "backend.workflows.cancel.SqlCancellationRepository.create",
        )
    ]
    assert confirm["survived"] == 1
    assert create["no tests"] == 1


def test_默认只显示有缺口的函数_基座豁免() -> None:
    output = render(parse(SAMPLE))
    assert "CancellationWorkflow.confirm" in output
    assert "SqlCancellationRepository.create" in output
    assert "render_result" in output
    assert "缺口合计=2" in output


def test_模块过滤_基座豁免() -> None:
    output = render(parse(SAMPLE), module="backend.domain")
    assert "render_result" in output
    assert "CancellationWorkflow.confirm" not in output
