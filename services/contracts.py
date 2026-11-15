"""契约文件加载：Gateway 与 Mock OMS 共用同一份解析与校验逻辑。"""

import json
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator
from referencing import Registry, Resource

ROOT = Path(__file__).resolve().parents[1]
CONTRACTS = ROOT / "packages" / "contracts"
TOOLS_DIR = CONTRACTS / "tools"
DOMAIN_PATH = CONTRACTS / "schemas" / "domain.json"


def load_domain() -> dict[str, Any]:
    document: dict[str, Any] = json.loads(DOMAIN_PATH.read_text(encoding="utf-8"))
    return document


def load_tool_documents() -> dict[str, dict[str, Any]]:
    documents: dict[str, dict[str, Any]] = {}
    for path in sorted(TOOLS_DIR.glob("*.json")):
        if path.name == "openapi.json":
            continue
        document: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
        documents[path.stem] = document
    return documents


def build_registry(domain: dict[str, Any], tools: dict[str, dict[str, Any]]) -> Registry:
    resources: list[tuple[str, Resource[Any]]] = [(domain["$id"], Resource.from_contents(domain))]
    resources.extend((doc["$id"], Resource.from_contents(doc)) for doc in tools.values())
    return Registry().with_resources(resources)


def validator_for(
    document: dict[str, Any],
    definition: str,
    registry: Registry,
) -> Draft202012Validator:
    return Draft202012Validator(
        {"$ref": f"{document['$id']}#/$defs/{definition}"}, registry=registry
    )
