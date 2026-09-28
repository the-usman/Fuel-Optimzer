"""Factory for the shared ``requests.Session`` used by every external API client.

Connections are pooled and a real User-Agent is always sent. Retries apply to connection
errors only: a read timeout or an HTTP error is never retried, so a slow provider cannot
multiply the number of external calls made by one request.
"""

from __future__ import annotations

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry


def build_http_session(user_agent: str, connect_retries: int) -> requests.Session:
    retry = Retry(
        total=connect_retries,
        connect=connect_retries,
        read=0,
        status=0,
        other=0,
        backoff_factor=0.2,
        allowed_methods=None,
    )
    adapter = HTTPAdapter(max_retries=retry, pool_connections=4, pool_maxsize=16)
    session = requests.Session()
    session.mount("https://", adapter)
    session.mount("http://", adapter)
    session.headers.update({"User-Agent": user_agent, "Accept": "application/json"})
    return session
