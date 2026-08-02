import os
import time
import logging
from typing import Optional
from aiohttp import web

logger = logging.getLogger("Nym")


class HealthServer:
    """Embedded lightweight HTTP web server for Render health checks and keep-alive monitoring."""

    def __init__(self, port: Optional[int] = None):
        self.port = port or int(os.getenv("PORT", 10000))
        self.start_time = time.time()
        self._app = web.Application()
        self._runner: Optional[web.AppRunner] = None
        self._site: Optional[web.TCPSite] = None
        self._setup_routes()

    def _setup_routes(self) -> None:
        self._app.router.add_get("/", self._handle_health)
        self._app.router.add_get("/health", self._handle_health)

    async def _handle_health(self, request: web.Request) -> web.Response:
        """Handle HTTP ping request from Render or uptime monitoring services."""
        uptime = round(time.time() - self.start_time, 2)
        data = {
            "status": "ok",
            "bot": "Nym",
            "uptime_seconds": uptime,
            "message": "Nym Bot health check operational"
        }
        return web.json_response(data, status=200)

    async def start(self) -> None:
        """Start non-blocking HTTP web server on configured port."""
        try:
            self._runner = web.AppRunner(self._app)
            await self._runner.setup()
            self._site = web.TCPSite(self._runner, "0.0.0.0", self.port)
            await self._site.start()
            logger.info(f"🌐 Health Check HTTP server running on port {self.port} (http://0.0.0.0:{self.port}/health)")
        except Exception as e:
            logger.error(f"Failed to start Health Server on port {self.port}: {e}", exc_info=True)

    async def stop(self) -> None:
        """Stop HTTP web server gracefully."""
        if self._runner:
            await self._runner.cleanup()
            logger.info("Health Check HTTP server stopped.")
