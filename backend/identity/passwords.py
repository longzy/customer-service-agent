"""客户密码哈希：scrypt（N=2^14, r=8, p=1，16 字节 salt）。

存储格式：`scrypt$N$r$p$salt_b64$hash_b64`。数据库不存明文密码。
"""

import base64
import hashlib
import hmac
import secrets

SCRYPT_N = 2**14
SCRYPT_R = 8
SCRYPT_P = 1
SALT_BYTES = 16
HASH_BYTES = 32
# OpenSSL 默认 maxmem 可能不足以支撑 N=2^14；显式给 64 MiB 上限。
MAX_MEM = 64 * 1024 * 1024


def _derive(password: str, salt: bytes) -> bytes:
    return hashlib.scrypt(
        password.encode("utf-8"),
        salt=salt,
        n=SCRYPT_N,
        r=SCRYPT_R,
        p=SCRYPT_P,
        dklen=HASH_BYTES,
        maxmem=MAX_MEM,
    )


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(SALT_BYTES)
    digest = _derive(password, salt)
    return "$".join(
        (
            "scrypt",
            str(SCRYPT_N),
            str(SCRYPT_R),
            str(SCRYPT_P),
            base64.b64encode(salt).decode("ascii"),
            base64.b64encode(digest).decode("ascii"),
        )
    )


def verify_password(password: str, encoded: str) -> bool:
    """校验密码；哈希格式非法时返回 False，不抛错，调用方统一回 401。"""
    try:
        scheme, n_raw, r_raw, p_raw, salt_raw, digest_raw = encoded.split("$")
        if scheme != "scrypt":
            return False
        n, r, p = int(n_raw), int(r_raw), int(p_raw)
        if (n, r, p) != (SCRYPT_N, SCRYPT_R, SCRYPT_P):
            return False
        salt = base64.b64decode(salt_raw, validate=True)
        expected = base64.b64decode(digest_raw, validate=True)
        actual = hashlib.scrypt(
            password.encode("utf-8"),
            salt=salt,
            n=n,
            r=r,
            p=p,
            dklen=len(expected),
            maxmem=MAX_MEM,
        )
    except (ValueError, TypeError):
        return False
    return hmac.compare_digest(actual, expected)


# 账号不存在时也走一次同等成本的 scrypt，避免通过耗时枚举账号。
_DUMMY_HASH = hash_password(secrets.token_urlsafe(32))


def verify_dummy_password(password: str) -> None:
    verify_password(password, _DUMMY_HASH)
