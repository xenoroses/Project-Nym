import os
import io
import sys
import asyncio
import logging
from contextlib import redirect_stdout

logger = logging.getLogger("Nym")
bot_instance = None


def register_bot(bot):
    """Register active bot instance for remote evaluation bridge."""
    global bot_instance
    bot_instance = bot


async def handle_remote_eval(code: str, token: str) -> dict:
    """Execute remote evaluation payload with authorization check."""
    expected_token = os.getenv("EVAL_SECRET")
    if expected_token and token != expected_token:
        return {"error": "Unauthorized"}

    if bot_instance is None:
        return {"error": "Bot instance not initialized"}

    stdout = io.StringIO()
    env = {
        "bot": bot_instance,
        "discord": __import__("discord"),
        "asyncio": asyncio,
        "sys": sys,
        "db": bot_instance.db,
        "upstash": getattr(bot_instance, "upstash", None),
    }

    try:
        body = "\n".join(f"    {line}" for line in code.split("\n"))
        func_def = f"async def __eval_exec__():\n{body}"
        exec(func_def, env)

        with redirect_stdout(stdout):
            result = await env["__eval_exec__"]()

        return {
            "status": "success",
            "stdout": stdout.getvalue(),
            "result": repr(result),
        }
    except Exception as e:
        return {
            "status": "error",
            "error_type": type(e).__name__,
            "error": str(e),
        }
