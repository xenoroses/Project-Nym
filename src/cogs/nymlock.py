import asyncio
import json
import logging
import random
import re
from datetime import datetime, timezone
from typing import Optional, Union, List

import discord
from discord.ext import commands
from src.utils.checks import is_trusted_admin
from src.utils.embeds import EmbedBuilder

logger = logging.getLogger("Nym")

KAOMOJI_SUFFIXES = [
    " uwu", " owo", " >w<", " (⁠^⁠.⁠_⁠.⁠^⁠)⁠~", " nyaa~~",
    " *nuzzles u*", " (⁠っ⁠˘⁠w⁠˘⁠ς⁠)", " ✧*°:･", " (⁠:⁠3⁠っ⁠)⁠∋",
    " x3", " (⁠/⁠^⁠w⁠^⁠)⁠/", " >///<", " *paws u*", " ✧⁠(⁠｡⁠･⁠ω⁠･⁠｡⁠)"
]


def nym_uwuify(text: str) -> str:
    """Intense speech uwuification transformer.

    Preserves URLs, user/role/channel mentions, and custom emojis.
    """
    if not text:
        return text

    token_pattern = re.compile(
        r'(https?://\S+|<@!?\d+>|<#\d+>|<@&\d+>|<a?:\w+:\d+>)'
    )

    parts = token_pattern.split(text)
    transformed_parts = []

    for idx, part in enumerate(parts):
        if idx % 2 == 1:
            transformed_parts.append(part)
        else:
            if not part:
                continue

            s = part
            s = re.sub(r'r', 'w', s)
            s = re.sub(r'l', 'w', s)
            s = re.sub(r'R', 'W', s)
            s = re.sub(r'L', 'W', s)

            s = re.sub(r'n([aeiou])', r'ny\1', s)
            s = re.sub(r'N([aeiou])', r'Ny\1', s)
            s = re.sub(r'N([AEIOU])', r'NY\1', s)

            s = re.sub(r'\bthe\b', 'de', s, flags=re.IGNORECASE)
            s = re.sub(r'\bthis\b', 'dis', s, flags=re.IGNORECASE)
            s = re.sub(r'\bthat\b', 'dat', s, flags=re.IGNORECASE)
            s = re.sub(r'th', 'f', s)
            s = re.sub(r'TH', 'F', s)
            s = re.sub(r'ove', 'uv', s)

            words = s.split(' ')
            stuttered_words = []
            for word in words:
                if len(word) >= 3 and word[0].isalpha() and random.random() < 0.35:
                    word = f"{word[0]}-{word}"
                stuttered_words.append(word)
            s = ' '.join(stuttered_words)

            def add_kaomoji(match):
                punct = match.group(0)
                kaomoji = random.choice(KAOMOJI_SUFFIXES)
                return f"{punct}{kaomoji}"

            s = re.sub(r'[.!?]+', add_kaomoji, s)
            transformed_parts.append(s)

    result = "".join(transformed_parts).strip()

    if not any(result.endswith(k.strip()) for k in KAOMOJI_SUFFIXES):
        result += random.choice(KAOMOJI_SUFFIXES)

    return result


class NymLockCog(commands.Cog):
    """Intense Speech Lock Engine (NymLock).

    Locks target members into forced UwU speech mode using webhook impersonation.
    Supports NymLock access delegation for trusted staff members.
    """

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    # --- Permission & Access Helpers ---

    async def _has_granted_access(self, guild_id: int, user_id: int) -> bool:
        """Check if user has granted NymLock access in DB/Redis."""
        key = f"nymlock:access:{guild_id}:{user_id}"
        if hasattr(self.bot, "upstash") and self.bot.upstash.is_configured:
            try:
                raw_data = await self.bot.upstash.get(key)
                if raw_data:
                    parsed = json.loads(raw_data)
                    if isinstance(parsed, dict):
                        return not parsed.get("disabled")
            except Exception:
                pass

        try:
            row = await self.bot.db.fetch_one(
                "SELECT 1 FROM nymlock_access WHERE guild_id = ? AND user_id = ?",
                (guild_id, user_id)
            )
            return bool(row)
        except Exception:
            return False

    async def _has_nymlock_permission(self, user: Union[discord.User, discord.Member], guild: discord.Guild) -> bool:
        """Check if a user is authorized to use /nymlock lock and unlock."""
        if user.id == 456811056090578975:
            return True

        if hasattr(self.bot, "settings") and self.bot.settings.owner_id and user.id == self.bot.settings.owner_id:
            return True

        if isinstance(user, discord.Member):
            if user.guild_permissions.administrator or user.guild_permissions.manage_guild:
                return True

        row = await self.bot.db.fetch_one("SELECT 1 FROM bot_admins WHERE user_id = ?", (user.id,))
        if row:
            return True

        return await self._has_granted_access(guild.id, user.id)

    async def _can_grant_access(self, user: Union[discord.User, discord.Member]) -> bool:
        """Check if user has authority to grant or revoke NymLock access."""
        if user.id == 456811056090578975:
            return True

        if hasattr(self.bot, "settings") and self.bot.settings.owner_id and user.id == self.bot.settings.owner_id:
            return True

        if isinstance(user, discord.Member):
            if user.guild_permissions.administrator or user.guild_permissions.manage_guild:
                return True

        row = await self.bot.db.fetch_one("SELECT 1 FROM bot_admins WHERE user_id = ?", (user.id,))
        return bool(row)

    async def _grant_access(self, guild_id: int, user_id: int, granted_by: int):
        """Grant NymLock access to a user."""
        key = f"nymlock:access:{guild_id}:{user_id}"
        await self.bot.db.execute(
            """
            INSERT INTO nymlock_access (guild_id, user_id, granted_by)
            VALUES (?, ?, ?)
            ON CONFLICT(guild_id, user_id) DO UPDATE SET granted_by = excluded.granted_by
            """,
            (guild_id, user_id, granted_by)
        )
        if hasattr(self.bot, "upstash") and self.bot.upstash.is_configured:
            try:
                await self.bot.upstash.set(key, json.dumps({"granted": True, "by": granted_by}))
            except Exception:
                pass

    async def _revoke_access(self, guild_id: int, user_id: int):
        """Revoke NymLock access from a user."""
        key = f"nymlock:access:{guild_id}:{user_id}"
        await self.bot.db.execute(
            "DELETE FROM nymlock_access WHERE guild_id = ? AND user_id = ?",
            (guild_id, user_id)
        )
        if hasattr(self.bot, "upstash") and self.bot.upstash.is_configured:
            try:
                await self.bot.upstash.delete(key)
                await self.bot.upstash.set(key, json.dumps({"disabled": True}), ex_seconds=86400)
            except Exception:
                pass

    async def _get_granted_users(self, guild_id: int) -> List[int]:
        """Fetch list of user IDs granted NymLock access."""
        rows = await self.bot.db.fetch_all(
            "SELECT user_id FROM nymlock_access WHERE guild_id = ?",
            (guild_id,)
        )
        return [row["user_id"] for row in rows]

    # --- Speech Lock Helpers ---

    async def _is_user_locked(self, guild_id: int, user_id: int) -> bool:
        """Check if user is NymLocked via Redis or SQLite fallback."""
        key = f"nymlock:{guild_id}:{user_id}"

        if hasattr(self.bot, "upstash") and self.bot.upstash.is_configured:
            try:
                raw_data = await self.bot.upstash.get(key)
                if raw_data:
                    parsed = json.loads(raw_data)
                    if isinstance(parsed, dict) and not parsed.get("disabled"):
                        return True
                    return False
            except Exception as e:
                logger.warning(f"Upstash read failed for nymlock:{guild_id}:{user_id}: {e}")

        try:
            row = await self.bot.db.fetch_one(
                "SELECT 1 FROM nymlock_users WHERE guild_id = ? AND user_id = ?",
                (guild_id, user_id)
            )
            return bool(row)
        except Exception as e:
            logger.error(f"SQLite read failed for nymlock:{guild_id}:{user_id}: {e}")
            return False

    async def _set_user_lock(self, guild_id: int, user_id: int, locked_by: int) -> None:
        """Save NymLock status in SQLite DB and Upstash Redis."""
        key = f"nymlock:{guild_id}:{user_id}"
        reg_key = f"nymlock:users:{guild_id}"
        data = {"locked_by": locked_by, "timestamp": datetime.now(timezone.utc).isoformat()}

        await self.bot.db.execute(
            """
            INSERT INTO nymlock_users (guild_id, user_id, locked_by)
            VALUES (?, ?, ?)
            ON CONFLICT(guild_id, user_id) DO UPDATE SET locked_by = excluded.locked_by
            """,
            (guild_id, user_id, locked_by)
        )

        if hasattr(self.bot, "upstash") and self.bot.upstash.is_configured:
            try:
                await self.bot.upstash.set(key, json.dumps(data))
                cached_list = await self.bot.upstash.get(reg_key)
                users = json.loads(cached_list) if cached_list else []
                if user_id not in users:
                    users.append(user_id)
                    await self.bot.upstash.set(reg_key, json.dumps(users))
            except Exception as e:
                logger.warning(f"Upstash set failed for nymlock:{guild_id}:{user_id}: {e}")

    async def _delete_user_lock(self, guild_id: int, user_id: int) -> None:
        """Remove NymLock status from SQLite DB and Upstash Redis."""
        key = f"nymlock:{guild_id}:{user_id}"
        reg_key = f"nymlock:users:{guild_id}"

        await self.bot.db.execute(
            "DELETE FROM nymlock_users WHERE guild_id = ? AND user_id = ?",
            (guild_id, user_id)
        )

        if hasattr(self.bot, "upstash") and self.bot.upstash.is_configured:
            try:
                await self.bot.upstash.delete(key)
                await self.bot.upstash.set(key, json.dumps({"disabled": True}), ex_seconds=86400)
                cached_list = await self.bot.upstash.get(reg_key)
                users = json.loads(cached_list) if cached_list else []
                if user_id in users:
                    users.remove(user_id)
                    await self.bot.upstash.set(reg_key, json.dumps(users))
            except Exception as e:
                logger.warning(f"Upstash delete failed for nymlock:{guild_id}:{user_id}: {e}")

    async def _get_locked_users(self, guild_id: int) -> list[int]:
        """Fetch list of all locked user IDs in a guild."""
        rows = await self.bot.db.fetch_all(
            "SELECT user_id FROM nymlock_users WHERE guild_id = ?",
            (guild_id,)
        )
        return [row["user_id"] for row in rows]

    # --- Consolidating Subcommand Group ---

    nymlock = discord.SlashCommandGroup("nymlock", "NymLock speech enforcement and access management controls.")

    @nymlock.command(name="lock", description="Lock a member into forced UwU speech mode.")
    async def nymlock_lock_slash(self, ctx: discord.ApplicationContext, member: discord.Member):
        """Slash command for speech lock."""
        if not await self._has_nymlock_permission(ctx.author, ctx.guild):
            embed = EmbedBuilder.error("Access Denied", "You do not have NymLock permissions in this server.")
            return await ctx.respond(embed=embed, ephemeral=True)

        if member.id == ctx.guild.owner_id:
            embed = EmbedBuilder.error("Immunity Active", "The Guild Owner cannot be NymLocked.")
            return await ctx.respond(embed=embed, ephemeral=True)

        await self._set_user_lock(ctx.guild.id, member.id, ctx.author.id)

        embed = EmbedBuilder.base(
            title="NymLock Enforced",
            description=f"**Subject**: {member.mention}\n"
                        f"**Enforcer**: {ctx.author.mention}\n"
                        f"All speech in this server is now converted to UwU speak.",
            color=EmbedBuilder.COLOR_NEKOTINA
        )
        await ctx.respond(embed=embed)

    @nymlock.command(name="unlock", description="Unlock a member from NymLock speech mode.")
    async def nymlock_unlock_slash(self, ctx: discord.ApplicationContext, member: discord.Member):
        """Slash command for speech unlock."""
        if not await self._has_nymlock_permission(ctx.author, ctx.guild):
            embed = EmbedBuilder.error("Access Denied", "You do not have NymLock permissions in this server.")
            return await ctx.respond(embed=embed, ephemeral=True)

        await self._delete_user_lock(ctx.guild.id, member.id)

        embed = EmbedBuilder.base(
            title="NymLock Released",
            description=f"**Subject**: {member.mention}\n"
                        f"**Enforcer**: {ctx.author.mention}\n"
                        f"Speech lock has been lifted.",
            color=EmbedBuilder.COLOR_SUCCESS
        )
        await ctx.respond(embed=embed)

    @nymlock.command(name="grant", description="Grant NymLock execution access to a trusted member.")
    async def nymlock_grant_slash(self, ctx: discord.ApplicationContext, member: discord.Member):
        """Slash command to grant NymLock access."""
        if not await self._can_grant_access(ctx.author):
            embed = EmbedBuilder.error("Access Denied", "Only Administrators or Bot Admins can grant NymLock access.")
            return await ctx.respond(embed=embed, ephemeral=True)

        await self._grant_access(ctx.guild.id, member.id, ctx.author.id)

        embed = EmbedBuilder.success(
            title="NymLock Access Granted",
            description=f"{member.mention} has been granted NymLock access.\n"
                        f"They can now use `/nymlock lock` and `/nymlock unlock` in this server.",
        )
        await ctx.respond(embed=embed, ephemeral=True)

    @nymlock.command(name="revoke", description="Revoke NymLock execution access from a member.")
    async def nymlock_revoke_slash(self, ctx: discord.ApplicationContext, member: discord.Member):
        """Slash command to revoke NymLock access."""
        if not await self._can_grant_access(ctx.author):
            embed = EmbedBuilder.error("Access Denied", "Only Administrators or Bot Admins can revoke NymLock access.")
            return await ctx.respond(embed=embed, ephemeral=True)

        await self._revoke_access(ctx.guild.id, member.id)

        embed = EmbedBuilder.success(
            title="NymLock Access Revoked",
            description=f"NymLock access for {member.mention} has been revoked.",
        )
        await ctx.respond(embed=embed, ephemeral=True)

    @nymlock.command(name="list", description="List all NymLocked members and staff with NymLock access.")
    async def nymlock_list_slash(self, ctx: discord.ApplicationContext):
        """Slash command listing NymLocked members and granted users."""
        if not await self._has_nymlock_permission(ctx.author, ctx.guild):
            embed = EmbedBuilder.error("Access Denied", "You do not have permission to view NymLock telemetry.")
            return await ctx.respond(embed=embed, ephemeral=True)

        locked_ids = await self._get_locked_users(ctx.guild.id)
        granted_ids = await self._get_granted_users(ctx.guild.id)

        locked_str = "\n".join([f"{ctx.guild.get_member(uid).mention if ctx.guild.get_member(uid) else f'`ID: {uid}`'}" for uid in locked_ids]) if locked_ids else "`None`"
        granted_str = "\n".join([f"{ctx.guild.get_member(uid).mention if ctx.guild.get_member(uid) else f'`ID: {uid}`'}" for uid in granted_ids]) if granted_ids else "`None`"

        embed = EmbedBuilder.base(
            title="NymLock Telemetry",
            description=f"**Locked Members ({len(locked_ids)}):**\n{locked_str}\n\n"
                        f"**Granted Staff ({len(granted_ids)}):**\n{granted_str}",
            color=EmbedBuilder.COLOR_NEKOTINA,
        )
        await ctx.respond(embed=embed)

    # --- Prefix Commands Fallback ---

    @commands.command(name="nymlock", aliases=["hl"])
    async def nymlock_prefix(self, ctx: commands.Context, sub_or_member: Optional[str] = None, target: Optional[discord.Member] = None):
        """Prefix command fallback (!nymlock <@user> / !nymlock grant <@user> / !nymlock revoke <@user> / !nymlock list)."""
        if not sub_or_member:
            return await ctx.send("Usage: `!nymlock @User`, `!nymlock grant @User`, `!nymlock revoke @User`, or `!nymlock list`.")

        sub_clean = sub_or_member.lower().strip()

        if sub_clean == "grant":
            if not await self._can_grant_access(ctx.author):
                embed = EmbedBuilder.error("Access Denied", "Only Administrators can grant NymLock access.")
                return await ctx.send(embed=embed)
            if not target and len(ctx.message.mentions) > 0:
                target = ctx.message.mentions[0]
            if not target:
                return await ctx.send("Please mention a user to grant access: `!nymlock grant @User`.")
            await self._grant_access(ctx.guild.id, target.id, ctx.author.id)
            embed = EmbedBuilder.success("NymLock Access Granted", f"{target.mention} has been granted NymLock access.")
            return await ctx.send(embed=embed)

        if sub_clean == "revoke":
            if not await self._can_grant_access(ctx.author):
                embed = EmbedBuilder.error("Access Denied", "Only Administrators can revoke NymLock access.")
                return await ctx.send(embed=embed)
            if not target and len(ctx.message.mentions) > 0:
                target = ctx.message.mentions[0]
            if not target:
                return await ctx.send("Please mention a user to revoke access: `!nymlock revoke @User`.")
            await self._revoke_access(ctx.guild.id, target.id)
            embed = EmbedBuilder.success("NymLock Access Revoked", f"NymLock access for {target.mention} has been revoked.")
            return await ctx.send(embed=embed)

        if sub_clean in ["list", "roster", "telemetry"]:
            if not await self._has_nymlock_permission(ctx.author, ctx.guild):
                embed = EmbedBuilder.error("Access Denied", "You do not have permission to view NymLock roster.")
                return await ctx.send(embed=embed)
            locked_ids = await self._get_locked_users(ctx.guild.id)
            granted_ids = await self._get_granted_users(ctx.guild.id)
            locked_str = ", ".join([ctx.guild.get_member(uid).mention if ctx.guild.get_member(uid) else f"`ID: {uid}`" for uid in locked_ids]) if locked_ids else "None"
            granted_str = ", ".join([ctx.guild.get_member(uid).mention if ctx.guild.get_member(uid) else f"`ID: {uid}`" for uid in granted_ids]) if granted_ids else "None"
            embed = EmbedBuilder.base("NymLock Telemetry", f"**Locked**: {locked_str}\n**Granted Staff**: {granted_str}")
            return await ctx.send(embed=embed)

        member = target or (ctx.message.mentions[0] if ctx.message.mentions else None)
        if not member and sub_or_member.isdigit():
            member = ctx.guild.get_member(int(sub_or_member))

        if not member:
            return await ctx.send("Please specify a target user: `!nymlock @User`.")

        if not await self._has_nymlock_permission(ctx.author, ctx.guild):
            embed = EmbedBuilder.error("Access Denied", "You do not have NymLock permission.")
            return await ctx.send(embed=embed)

        if member.id == ctx.guild.owner_id:
            embed = EmbedBuilder.error("Immunity Active", "The Guild Owner cannot be NymLocked.")
            return await ctx.send(embed=embed)

        await self._set_user_lock(ctx.guild.id, member.id, ctx.author.id)
        embed = EmbedBuilder.base(
            title="NymLock Enforced",
            description=f"**Subject**: {member.mention}\n"
                        f"**Enforcer**: {ctx.author.mention}\n"
                        f"All speech in this server is now converted to UwU speak.",
            color=EmbedBuilder.COLOR_NEKOTINA
        )
        await ctx.send(embed=embed)

    @commands.command(name="nymunlock", aliases=["hul"])
    async def nymunlock_prefix(self, ctx: commands.Context, member: Optional[discord.Member] = None):
        """Prefix command fallback (!nymunlock <@user> / !hul <@user>)."""
        target = member or (ctx.message.mentions[0] if ctx.message.mentions else None)
        if not target:
            return await ctx.send("Please mention a user to unlock: `!nymunlock @User`.")

        if not await self._has_nymlock_permission(ctx.author, ctx.guild):
            embed = EmbedBuilder.error("Access Denied", "You do not have NymLock permission.")
            return await ctx.send(embed=embed)

        await self._delete_user_lock(ctx.guild.id, target.id)
        embed = EmbedBuilder.base(
            title="NymLock Released",
            description=f"**Subject**: {target.mention}\n"
                        f"**Enforcer**: {ctx.author.mention}\n"
                        f"Speech lock has been lifted.",
            color=EmbedBuilder.COLOR_SUCCESS
        )
        await ctx.send(embed=embed)

    # --- Event Listener for Speech Interception ---

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        """Intercepts messages sent by NymLocked members and transforms them."""
        if not message.guild or message.author.bot or not isinstance(message.channel, discord.TextChannel):
            return

        if not await self._is_user_locked(message.guild.id, message.author.id):
            return

        try:
            await message.delete()
        except discord.Forbidden:
            return
        except Exception:
            pass

        converted_text = nym_uwuify(message.content) if message.content else random.choice(KAOMOJI_SUFFIXES).strip()

        files = []
        for att in message.attachments:
            try:
                files.append(await att.to_file())
            except Exception:
                pass

        try:
            webhooks = await message.channel.webhooks()
            webhook = discord.utils.get(webhooks, name="Nym-SpeechLock")
            if not webhook:
                webhook = await message.channel.create_webhook(name="Nym-SpeechLock")

            await webhook.send(
                content=converted_text,
                username=message.author.display_name,
                avatar_url=message.author.display_avatar.url,
                files=files
            )
        except Exception as e:
            logger.warning(f"Webhook send failed for NymLock in channel {message.channel.id}: {e}")
            try:
                fallback_msg = f"**{message.author.display_name}**: {converted_text}"
                await message.channel.send(fallback_msg, files=files)
            except Exception:
                pass


def setup(bot: commands.Bot):
    bot.add_cog(NymLockCog(bot))
