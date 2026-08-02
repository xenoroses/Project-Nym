import json
import logging
from typing import Optional, List, Union
import discord
from discord.ext import commands
from src.utils.embeds import EmbedBuilder

logger = logging.getLogger("Nym")
DEFAULT_PREFIXES = ["!", ","]


class PrefixCog(commands.Cog):
    """Custom Prefix Management Cog.

    Allows server administrators to set, add, remove, and reset custom command prefixes.
    Automatically synchronizes with SQLite storage and Upstash Redis caching.
    """

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    # --- Storage Helpers ---

    async def _get_guild_prefixes(self, guild_id: int) -> List[str]:
        """Fetch current custom prefixes for a guild."""
        cache_key = f"prefixes:{guild_id}"

        # 1. Check Upstash Redis Cache
        if hasattr(self.bot, "upstash") and self.bot.upstash.is_configured:
            try:
                cached = await self.bot.upstash.get(cache_key)
                if cached:
                    return json.loads(cached)
            except Exception as e:
                logger.warning(f"Upstash read error for {cache_key}: {e}")

        # 2. Check SQLite DB
        try:
            row = await self.bot.db.fetch_one("SELECT prefix FROM guild_settings WHERE guild_id = ?", (guild_id,))
            if row and row["prefix"]:
                try:
                    prefixes = json.loads(row["prefix"])
                    if isinstance(prefixes, list):
                        return prefixes
                    return [row["prefix"]]
                except Exception:
                    return [row["prefix"]]
        except Exception as e:
            logger.error(f"SQLite read error for guild {guild_id}: {e}")

        return DEFAULT_PREFIXES.copy()

    async def _save_guild_prefixes(self, guild_id: int, prefixes: List[str]) -> None:
        """Save updated custom prefixes to SQLite DB and Upstash Redis cache."""
        json_str = json.dumps(prefixes)
        cache_key = f"prefixes:{guild_id}"

        # 1. Update SQLite DB
        await self.bot.db.execute(
            """
            INSERT INTO guild_settings (guild_id, prefix)
            VALUES (?, ?)
            ON CONFLICT(guild_id) DO UPDATE SET prefix = excluded.prefix
            """,
            (guild_id, json_str)
        )

        # 2. Update Upstash Redis Cache
        if hasattr(self.bot, "upstash") and self.bot.upstash.is_configured:
            try:
                await self.bot.upstash.set(cache_key, json_str)
            except Exception as e:
                logger.warning(f"Upstash set error for {cache_key}: {e}")

    # --- Slash Commands ---

    prefix_group = discord.SlashCommandGroup(
        name="prefix",
        description="Manage server command prefixes."
    )

    @prefix_group.command(name="set", description="Set a primary custom prefix for this server (e.g. nym, ?, .).")
    @commands.has_permissions(manage_guild=True)
    async def prefix_set_slash(self, ctx: discord.ApplicationContext, prefix: str):
        """Set a single custom prefix for the server."""
        new_prefix = prefix.strip()

        if len(new_prefix) > 10:
            embed = EmbedBuilder.error("Invalid Prefix", "Prefix length cannot exceed 10 characters.")
            return await ctx.respond(embed=embed, ephemeral=True)

        new_prefixes = [new_prefix]
        await self._save_guild_prefixes(ctx.guild.id, new_prefixes)

        embed = EmbedBuilder.success(
            title="Prefix Updated",
            description=f"✅ Server custom prefix set to: `{new_prefix}`\n\n"
                        f"Example command: `{new_prefix}ping` or `!ping` or {self.bot.user.mention} `ping`"
        )
        await ctx.respond(embed=embed, ephemeral=True)

    @prefix_group.command(name="add", description="Add an additional command prefix to this server.")
    @commands.has_permissions(manage_guild=True)
    async def prefix_add_slash(self, ctx: discord.ApplicationContext, prefix: str):
        """Add an extra prefix to the server."""
        add_p = prefix.strip()

        current = await self._get_guild_prefixes(ctx.guild.id)
        if add_p in current:
            embed = EmbedBuilder.warning("Prefix Exists", f"`{add_p}` is already an active prefix.")
            return await ctx.respond(embed=embed, ephemeral=True)

        current.append(add_p)
        await self._save_guild_prefixes(ctx.guild.id, current)

        formatted_list = ", ".join(f"`{p}`" for p in current)
        embed = EmbedBuilder.success(
            title="Prefix Added",
            description=f"✅ Added `{add_p}` to server prefixes.\n\n**Active Prefixes:** {formatted_list}"
        )
        await ctx.respond(embed=embed, ephemeral=True)

    @prefix_group.command(name="remove", description="Remove a specific command prefix from this server.")
    @commands.has_permissions(manage_guild=True)
    async def prefix_remove_slash(self, ctx: discord.ApplicationContext, prefix: str):
        """Remove a prefix from the server."""
        rem_p = prefix.strip()

        current = await self._get_guild_prefixes(ctx.guild.id)
        if rem_p not in current:
            embed = EmbedBuilder.warning("Prefix Not Found", f"`{rem_p}` is not currently set as a prefix.")
            return await ctx.respond(embed=embed, ephemeral=True)

        if len(current) <= 1:
            embed = EmbedBuilder.error("Cannot Remove", "You must keep at least one custom prefix (or use `/prefix reset`).")
            return await ctx.respond(embed=embed, ephemeral=True)

        current.remove(rem_p)
        await self._save_guild_prefixes(ctx.guild.id, current)

        formatted_list = ", ".join(f"`{p}`" for p in current)
        embed = EmbedBuilder.success(
            title="Prefix Removed",
            description=f"✅ Removed `{rem_p}`.\n\n**Active Prefixes:** {formatted_list}"
        )
        await ctx.respond(embed=embed, ephemeral=True)

    @prefix_group.command(name="reset", description="Reset server prefixes back to default (!).")
    @commands.has_permissions(manage_guild=True)
    async def prefix_reset_slash(self, ctx: discord.ApplicationContext):
        """Reset server prefixes to default."""
        await self._save_guild_prefixes(ctx.guild.id, DEFAULT_PREFIXES.copy())

        embed = EmbedBuilder.success(
            title="Prefixes Reset",
            description=f"✅ Server prefixes reset back to default: `!` and `,`"
        )
        await ctx.respond(embed=embed, ephemeral=True)


    @prefix_group.command(name="list", description="Display all active prefixes for this server.")
    async def prefix_list_slash(self, ctx: discord.ApplicationContext):
        """List active server prefixes."""
        current = await self._get_guild_prefixes(ctx.guild.id)
        formatted = ", ".join(f"`{p}`" for p in current)

        embed = EmbedBuilder.info(
            title="⚙️ Server Command Prefixes",
            description=f"**Active Prefixes:** {formatted}\n**Bot Mention:** {self.bot.user.mention}"
        )
        await ctx.respond(embed=embed)

    # --- Prefix Command Group (!prefix set <prefix>, !prefix add <prefix>, etc.) ---

    @commands.group(name="prefix", invoke_without_command=True)
    async def prefix_group_cmd(self, ctx: commands.Context):
        """Prefix command handler (!prefix). Shows current prefixes if no subcommand passed."""
        if ctx.guild:
            current = await self._get_guild_prefixes(ctx.guild.id)
            formatted = ", ".join(f"`{p}`" for p in current)
            await ctx.send(f"⚙️ **Active Server Prefixes:** {formatted} (or mention {self.bot.user.mention})")
        else:
            await ctx.send("⚙️ **Default Direct Message Prefixes:** `!`, `,`")

    @prefix_group_cmd.command(name="set")
    @commands.has_permissions(manage_guild=True)
    async def prefix_set_cmd(self, ctx: commands.Context, *, prefix: str):
        """Set a single custom prefix (!prefix set <prefix>)."""
        new_prefix = prefix.strip()
        if len(new_prefix) > 10:
            return await ctx.send("❌ Prefix length cannot exceed 10 characters.")

        await self._save_guild_prefixes(ctx.guild.id, [new_prefix])
        await ctx.send(f"✅ Server custom prefix set to: `{new_prefix}` (Example: `{new_prefix}ping`)")

    @prefix_group_cmd.command(name="add")
    @commands.has_permissions(manage_guild=True)
    async def prefix_add_cmd(self, ctx: commands.Context, *, prefix: str):
        """Add an extra prefix (!prefix add <prefix>)."""
        add_p = prefix.strip()
        current = await self._get_guild_prefixes(ctx.guild.id)
        if add_p in current:
            return await ctx.send(f"⚠️ `{add_p}` is already an active prefix.")

        current.append(add_p)
        await self._save_guild_prefixes(ctx.guild.id, current)
        formatted = ", ".join(f"`{p}`" for p in current)
        await ctx.send(f"✅ Added `{add_p}`. **Active Prefixes:** {formatted}")

    @prefix_group_cmd.command(name="remove")
    @commands.has_permissions(manage_guild=True)
    async def prefix_remove_cmd(self, ctx: commands.Context, *, prefix: str):
        """Remove a prefix (!prefix remove <prefix>)."""
        rem_p = prefix.strip()
        current = await self._get_guild_prefixes(ctx.guild.id)
        if rem_p not in current:
            return await ctx.send(f"⚠️ `{rem_p}` is not currently an active prefix.")

        if len(current) <= 1:
            return await ctx.send("❌ Cannot remove the last prefix. Use `!prefix reset` to restore defaults.")

        current.remove(rem_p)
        await self._save_guild_prefixes(ctx.guild.id, current)
        formatted = ", ".join(f"`{p}`" for p in current)
        await ctx.send(f"✅ Removed `{rem_p}`. **Active Prefixes:** {formatted}")

    @prefix_group_cmd.command(name="reset")
    @commands.has_permissions(manage_guild=True)
    async def prefix_reset_cmd(self, ctx: commands.Context):
        """Reset prefixes back to default (!prefix reset)."""
        await self._save_guild_prefixes(ctx.guild.id, DEFAULT_PREFIXES.copy())
        await ctx.send("✅ Server prefixes reset back to default: `!` and `,`")

    @prefix_group_cmd.command(name="list")
    async def prefix_list_cmd(self, ctx: commands.Context):
        """List active server prefixes (!prefix list)."""
        if ctx.guild:
            current = await self._get_guild_prefixes(ctx.guild.id)
            formatted = ", ".join(f"`{p}`" for p in current)
            await ctx.send(f"⚙️ **Active Server Prefixes:** {formatted}")
        else:
            await ctx.send("⚙️ **Default Direct Message Prefixes:** `!`, `,`")


def setup(bot: commands.Bot):
    bot.add_cog(PrefixCog(bot))
