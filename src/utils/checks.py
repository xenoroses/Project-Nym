import json
import logging
from typing import Union
import discord
from discord.ext import commands

logger = logging.getLogger("Nym")


async def is_trusted_admin(ctx: Union[discord.ApplicationContext, commands.Context]) -> bool:
    """Check if the command invoker is the Bot Owner or a registered Bot Admin."""
    author_id = ctx.author.id

    # 1. Check if configured as Bot Owner in settings
    if hasattr(ctx.bot, "settings") and ctx.bot.settings.owner_id:
        if author_id == ctx.bot.settings.owner_id:
            return True

    # 2. Check via Py-Cord built-in is_owner check
    try:
        if await ctx.bot.is_owner(ctx.author):
            return True
    except Exception:
        pass

    # 3. Check Upstash Redis cache for bot_admins
    if hasattr(ctx.bot, "upstash") and ctx.bot.upstash.is_configured:
        try:
            cached = await ctx.bot.upstash.get("bot_admins")
            if cached:
                admin_list = json.loads(cached)
                if isinstance(admin_list, list) and author_id in admin_list:
                    return True
        except Exception as e:
            logger.warning(f"Upstash Redis bot_admins read failed: {e}")

    # 4. Check SQLite DB
    if hasattr(ctx.bot, "db"):
        try:
            row = await ctx.bot.db.fetch_one(
                "SELECT 1 FROM bot_admins WHERE user_id = ?",
                (author_id,)
            )
            if row:
                return True
        except Exception as e:
            logger.error(f"SQLite bot_admins query error: {e}")

    return False
