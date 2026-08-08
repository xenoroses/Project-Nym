import json
import logging
import discord
from discord.ext import commands
from src.utils.embeds import EmbedBuilder
from src.utils.checks import is_trusted_admin

logger = logging.getLogger("Nym")


class AdminCog(commands.Cog):
    """Bot Admin Management Cog for Project Nym."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    async def _sync_redis_admins(self) -> None:
        """Sync bot admins list from SQLite to Upstash Redis."""
        if hasattr(self.bot, "upstash") and self.bot.upstash.is_configured:
            try:
                rows = await self.bot.db.fetch_all("SELECT user_id FROM bot_admins")
                admin_ids = [row["user_id"] for row in rows]
                await self.bot.upstash.set("bot_admins", json.dumps(admin_ids))
            except Exception as e:
                logger.warning(f"Failed to sync bot_admins to Upstash Redis: {e}")

    async def _is_owner_check(self, ctx: commands.Context) -> bool:
        """Verify if invoker is Bot Owner."""
        if hasattr(self.bot, "settings") and self.bot.settings.owner_id:
            if ctx.author.id == self.bot.settings.owner_id:
                return True
        try:
            return await self.bot.is_owner(ctx.author)
        except Exception:
            return False

    # --- Commands ---

    @commands.command(name="addadmin")
    async def add_admin(self, ctx: commands.Context, user: discord.User):
        """[Owner Only] Grant global Bot Admin privileges to a user."""
        if not await self._is_owner_check(ctx):
            embed = EmbedBuilder.error("Access Denied", "Only the Bot Owner can add bot admins.")
            return await ctx.send(embed=embed)

        await self.bot.db.execute(
            """
            INSERT INTO bot_admins (user_id, added_by)
            VALUES (?, ?)
            ON CONFLICT(user_id) DO UPDATE SET added_by = excluded.added_by
            """,
            (user.id, ctx.author.id)
        )
        await self._sync_redis_admins()

        embed = EmbedBuilder.success(
            title="Bot Admin Added",
            description=f"✅ Granted trusted Bot Admin privileges to **{user.mention}** (`ID: {user.id}`).",
            author=ctx.author
        )
        await ctx.send(embed=embed)

    @commands.command(name="removeadmin")
    async def remove_admin(self, ctx: commands.Context, user: discord.User):
        """[Owner Only] Revoke global Bot Admin privileges from a user."""
        if not await self._is_owner_check(ctx):
            embed = EmbedBuilder.error("Access Denied", "Only the Bot Owner can remove bot admins.")
            return await ctx.send(embed=embed)

        await self.bot.db.execute("DELETE FROM bot_admins WHERE user_id = ?", (user.id,))
        await self._sync_redis_admins()

        embed = EmbedBuilder.success(
            title="Bot Admin Removed",
            description=f"⌬ Revoked Bot Admin privileges from **{user.mention}** (`ID: {user.id}`).",
            author=ctx.author
        )
        await ctx.send(embed=embed)

    @commands.command(name="listadmins")
    async def list_admins(self, ctx: commands.Context):
        """List all registered Bot Admins."""
        if not await is_trusted_admin(ctx):
            embed = EmbedBuilder.error("Access Denied", "Only Bot Owners and trusted Bot Admins can view this list.")
            return await ctx.send(embed=embed)

        rows = await self.bot.db.fetch_all("SELECT user_id, added_at FROM bot_admins")

        owner_id = getattr(self.bot.settings, "owner_id", None)
        owner_str = f"👑 **Owner ID:** `{owner_id}`\n\n" if owner_id else ""

        if not rows:
            description = f"{owner_str}*No additional Bot Admins registered.*"
        else:
            admin_entries = []
            for row in rows:
                user_id = row["user_id"]
                admin_entries.append(f"• <@{user_id}> (`{user_id}`)")
            description = f"{owner_str}**Registered Trusted Admins:**\n" + "\n".join(admin_entries)

        embed = EmbedBuilder.base(
            title="⚡ Nym Bot Admins & Access Control",
            description=description,
            color=EmbedBuilder.COLOR_NEKOTINA,
            author=ctx.author
        )
        await ctx.send(embed=embed)

    @commands.command(name="sync")
    async def sync_commands_prefix(self, ctx: commands.Context):
        """[Trusted Admin Only] Force sync slash commands with Discord API."""
        if not await is_trusted_admin(ctx):
            embed = EmbedBuilder.error("Access Denied", "Only trusted admins can run command sync.")
            return await ctx.send(embed=embed)

        try:
            await self.bot.sync_commands()
            cmd_count = len(self.bot.pending_application_commands)
            embed = EmbedBuilder.base(
                title="✧ Gates Synced",
                description=f"✧ Synced `{cmd_count}` gates globally.",
                color=EmbedBuilder.COLOR_NEKOTINA,
                author=ctx.author
            )
            await ctx.send(embed=embed)
        except Exception as e:
            embed = EmbedBuilder.error("Sync Error", f"Failed syncing gates: `{e}`")
            await ctx.send(embed=embed)



def setup(bot: commands.Bot):
    bot.add_cog(AdminCog(bot))

