import logging
import time
from typing import Optional, Any
import aiohttp

logger = logging.getLogger("Nym")


class UpstashRedis:
    """Async Upstash Redis REST API Client using aiohttp."""

    def __init__(self, rest_url: Optional[str], rest_token: Optional[str]):
        self.url = rest_url.rstrip("/") if rest_url else None
        self.token = rest_token
        self._session: Optional[aiohttp.ClientSession] = None

    @property
    def is_configured(self) -> bool:
        """Check if Upstash Redis credentials are present."""
        return bool(self.url and self.token)

    async def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            headers = {"Authorization": f"Bearer {self.token}"}
            self._session = aiohttp.ClientSession(headers=headers)
        return self._session

    async def ping(self) -> float:
        """Ping Upstash Redis REST endpoint and return latency in ms.

        Returns:
            Latency in milliseconds. Raises Exception if ping fails.
        """
        if not self.is_configured:
            raise ValueError("Upstash Redis credentials are not configured in environment.")

        session = await self._get_session()
        start = time.perf_counter()
        async with session.get(f"{self.url}/ping") as response:
            latency = (time.perf_counter() - start) * 1000
            if response.status == 200:
                return round(latency, 2)
            else:
                body = await response.text()
                raise RuntimeError(f"Upstash ping failed [{response.status}]: {body}")

    async def set(self, key: str, value: str, ex_seconds: Optional[int] = None) -> bool:
        """Set key value in Upstash Redis."""
        if not self.is_configured:
            return False

        session = await self._get_session()
        endpoint = f"{self.url}/set/{key}/{value}"
        if ex_seconds:
            endpoint += f"/EX/{ex_seconds}"

        async with session.post(endpoint) as response:
            return response.status == 200

    async def get(self, key: str) -> Optional[str]:
        """Get value by key from Upstash Redis."""
        if not self.is_configured:
            return None

        session = await self._get_session()
        async with session.get(f"{self.url}/get/{key}") as response:
            if response.status == 200:
                data = await response.json()
                return data.get("result")
            return None

    async def close(self) -> None:
        """Close HTTP session."""
        if self._session and not self._session.closed:
            await self._session.close()
