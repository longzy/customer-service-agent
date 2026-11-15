"""OpenAPI 片段必须由 Tool 契约生成，且与契约保持同步。

生成物与结构断言不对应具体 AC，按基座豁免处理。
"""

import json
from pathlib import Path

from scripts.gen_tool_openapi import build

OPENAPI = Path("packages/contracts/tools/openapi.json")


def test_openapi片段与契约同步_基座豁免() -> None:
    expected = build()
    actual = json.loads(OPENAPI.read_text(encoding="utf-8"))
    assert actual == expected


def test_openapi包含全部Tool_基座豁免() -> None:
    doc = build()
    assert set(doc["paths"]) == {
        "/tools/list_recent_orders",
        "/tools/get_order",
        "/tools/get_cancel_eligibility",
        "/tools/submit_cancel",
        "/tools/get_cancel_result",
    }
    assert "ErrorEnvelope" in doc["components"]["schemas"]


def collect_refs(node: object) -> set[str]:
    refs: set[str] = set()
    if isinstance(node, dict):
        for key, value in node.items():
            if key == "$ref" and isinstance(value, str):
                refs.add(value.split("/")[-1])
            else:
                refs |= collect_refs(value)
    elif isinstance(node, list):
        for item in node:
            refs |= collect_refs(item)
    return refs


def test_每个操作都有必填请求体与响应描述_基座豁免() -> None:
    doc = build()
    for path, operation in doc["paths"].items():
        post = operation["post"]
        assert post["requestBody"]["required"] is True, path
        for status, response in post["responses"].items():
            assert response.get("description"), f"{path} {status} 缺少 description"


def test_paths通过引用指向components_基座豁免() -> None:
    doc = build()
    for path, operation in doc["paths"].items():
        post = operation["post"]
        request_schema = post["requestBody"]["content"]["application/json"]["schema"]
        assert set(request_schema) == {"$ref"}, path
        for status, response in post["responses"].items():
            schema = response["content"]["application/json"]["schema"]
            assert set(schema) == {"$ref"}, f"{path} {status}"


def test_所有引用都指向存在的组件_基座豁免() -> None:
    doc = build()
    names = set(doc["components"]["schemas"])
    missing = collect_refs(doc) - names
    assert missing == set(), f"悬空引用：{sorted(missing)}"


def test_components没有孤立定义_基座豁免() -> None:
    doc = build()
    schemas = doc["components"]["schemas"]
    reachable = collect_refs(doc["paths"])
    frontier = set(reachable)
    while frontier:
        name = frontier.pop()
        for ref in collect_refs(schemas.get(name, {})):
            if ref not in reachable:
                reachable.add(ref)
                frontier.add(ref)
    orphans = set(schemas) - reachable
    assert orphans == set(), f"以下组件未被引用：{sorted(orphans)}"
