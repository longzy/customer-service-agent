"""由 Tool 契约生成 OpenAPI 片段，避免手写与 Schema 漂移。

用法：python3 scripts/gen_tool_openapi.py [--check]
"""

import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
SCHEMAS = ROOT / "packages" / "contracts" / "schemas"
TOOLS = ROOT / "packages" / "contracts" / "tools"
OUTPUT = TOOLS / "openapi.json"

TOOL_NAMES = (
    "list_recent_orders",
    "get_order",
    "get_cancel_eligibility",
    "submit_cancel",
    "get_cancel_result",
)


def load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def rewrite_refs(node: Any) -> Any:
    """把工具内的 $ref 统一指向 components/schemas。"""
    if isinstance(node, dict):
        if "$ref" in node and isinstance(node["$ref"], str):
            ref = node["$ref"].split("#/")[-1].replace("$defs/", "")
            return {"$ref": f"#/components/schemas/{ref}"}
        return {key: rewrite_refs(value) for key, value in node.items()}
    if isinstance(node, list):
        return [rewrite_refs(item) for item in node]
    return node


def _collect_refs(node: Any) -> set[str]:
    refs: set[str] = set()
    if isinstance(node, dict):
        for key, value in node.items():
            if key == "$ref" and isinstance(value, str):
                refs.add(value.split("/")[-1])
            else:
                refs |= _collect_refs(value)
    elif isinstance(node, list):
        for item in node:
            refs |= _collect_refs(item)
    return refs


def _prune_unreferenced(paths: dict[str, Any], components: dict[str, Any]) -> dict[str, Any]:
    """只保留从 paths 可达的组件，避免生成孤立定义。"""
    reachable: set[str] = set()
    frontier = list(_collect_refs(paths))
    while frontier:
        name = frontier.pop()
        if name in reachable or name not in components:
            continue
        reachable.add(name)
        frontier.extend(_collect_refs(components[name]))
    return {name: schema for name, schema in components.items() if name in reachable}


def component_name(tool: str, kind: str) -> str:
    return "".join(part.capitalize() for part in tool.split("_")) + kind


def build() -> dict[str, Any]:
    domain = load(SCHEMAS / "domain.json")
    components: dict[str, Any] = {
        name: rewrite_refs(schema) for name, schema in domain["$defs"].items()
    }
    paths: dict[str, Any] = {}

    for name in TOOL_NAMES:
        doc = load(TOOLS / f"{name}.json")
        request_name = component_name(name, "Request")
        response_name = component_name(name, "Response")
        components[request_name] = rewrite_refs(doc["$defs"]["Request"])
        components[response_name] = rewrite_refs(doc["$defs"]["Response"])
        paths[f"/tools/{name}"] = {
            "post": {
                "operationId": name,
                "summary": f"调用 {name}",
                "requestBody": {
                    "required": True,
                    "content": {
                        "application/json": {
                            "schema": {"$ref": f"#/components/schemas/{request_name}"}
                        }
                    },
                },
                "responses": {
                    "200": {
                        "description": "成功响应",
                        "content": {
                            "application/json": {
                                "schema": {"$ref": f"#/components/schemas/{response_name}"}
                            }
                        },
                    },
                    "default": {
                        "description": "统一错误封套",
                        "content": {
                            "application/json": {
                                "schema": {"$ref": "#/components/schemas/ErrorEnvelope"}
                            }
                        },
                    },
                },
                "x-error-codes": doc["x-error-codes"],
            }
        }

    components = _prune_unreferenced(paths, components)
    return {
        "openapi": "3.1.0",
        "info": {"title": "M1 Tool 契约", "version": "0.1.0"},
        "paths": paths,
        "components": {"schemas": components},
    }


def main() -> int:
    document = build()
    text = json.dumps(document, ensure_ascii=False, indent=2) + "\n"
    if "--check" in sys.argv:
        current = OUTPUT.read_text(encoding="utf-8") if OUTPUT.exists() else ""
        if current != text:
            print("openapi.json 与契约不同步，请运行 python3 scripts/gen_tool_openapi.py")
            return 1
        print("openapi.json 与契约同步")
        return 0
    OUTPUT.write_text(text, encoding="utf-8")
    print(f"已生成 {OUTPUT.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
