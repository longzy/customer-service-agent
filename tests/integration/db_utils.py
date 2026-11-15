"""集成测试的数据库可用性判断。"""

import socket
from urllib.parse import urlparse

from services.api.settings import settings


def db_available() -> bool:
    url = urlparse(settings.database_url.replace("+asyncpg", ""))
    try:
        with socket.create_connection((url.hostname or "127.0.0.1", url.port or 5432), timeout=0.3):
            return True
    except OSError:
        return False
