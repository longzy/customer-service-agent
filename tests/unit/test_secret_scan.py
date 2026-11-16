"""密钥扫描脚本的自检：能识别常见密钥，不误报占位符（基座豁免）。"""

import importlib.util
from pathlib import Path

SCRIPT = Path("scripts/check-secrets.py")


def scanner():
    spec = importlib.util.spec_from_file_location("check_secrets", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_识别模型密钥_基座豁免() -> None:
    # 用拼接构造样本，避免测试文件本身被扫描命中
    sample = "MODEL_API_KEY=" + "sk-" + "a" * 32
    assert scanner().scan_text(sample), "未识别模型密钥"


def test_识别云厂商密钥_基座豁免() -> None:
    sample = "AKIA" + "ABCDEFGHIJKLMNOP"
    assert scanner().scan_text(sample), "未识别 AWS 访问密钥"


def test_忽略占位符_基座豁免() -> None:
    assert scanner().scan_text("MODEL_API_KEY=sk-your-key-here") == []
    assert scanner().scan_text("MODEL_API_KEY=<在本地填写>") == []


def test_行尾注释不能豁免_基座豁免() -> None:
    sample = "MODEL_API_KEY=" + "sk-" + "a" * 32 + "  # example"
    assert scanner().scan_text(sample), "加注释就漏报，等同于没有扫描"


def test_忽略环境变量读取_基座豁免() -> None:
    assert scanner().scan_text('api_key = os.environ["MODEL_API_KEY"]') == []


def test_仓库当前没有泄漏_基座豁免() -> None:
    findings = scanner().scan_repository()
    assert findings == [], f"发现疑似密钥：{findings}"
