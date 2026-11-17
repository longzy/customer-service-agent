"""OpenAPI 契约与生成类型的一致性（基座豁免）。"""

import importlib.util
import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
SPEC = ROOT / "packages" / "contracts" / "openapi.json"
TYPES = ROOT / "apps" / "chat" / "lib" / "api-types.ts"

EXPECTED = {
    "/customer/sessions": "CustomerSessionResponse",
    "/customer/session": "CustomerSessionResponse",
    "/customer/conversations/{conversation_id}": "CustomerSessionResponse",
    "/customer/messages": "MessagePageResponse",
}


def _load_export_module() -> Any:
    path = ROOT / "scripts" / "export_openapi.py"
    spec = importlib.util.spec_from_file_location("export_openapi", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _document() -> dict[str, Any]:
    return json.loads(SPEC.read_text(encoding="utf-8"))


def test_openapi快照与运行时一致_基座豁免() -> None:
    module = _load_export_module()
    rendered = module.render(module.build_spec())
    assert SPEC.read_text(encoding="utf-8") == rendered


def test_客户接口响应有明确模型_基座豁免() -> None:
    document = _document()
    for path, schema in EXPECTED.items():
        method = "post" if path == "/customer/sessions" else "get"
        operation = document["paths"][path][method]
        response_schema = operation["responses"]["200"]["content"]["application/json"]["schema"]
        assert response_schema["$ref"].endswith("/" + schema)
        assert document["components"]["schemas"][schema]["additionalProperties"] is False


def test_错误封套进入契约_基座豁免() -> None:
    document = _document()
    envelope = document["components"]["schemas"]["ErrorEnvelope"]
    assert set(envelope["required"]) == {"code", "retryable", "visible", "message"}
    login = document["paths"]["/customer/sessions"]["post"]
    assert login["responses"]["401"]["content"]["application/json"]["schema"]["$ref"].endswith(
        "/ErrorEnvelope"
    )


def test_生成类型包含客户契约_基座豁免() -> None:
    content = TYPES.read_text(encoding="utf-8")
    for name in (
        "CustomerSessionResponse",
        "MessagePageResponse",
        "MessagePublic",
        "ErrorEnvelope",
        '"AI_ACTIVE"',
    ):
        assert name in content
    assert "Do not make direct changes" in content
