import asyncio
import json
import logging
import random
import re
from datetime import datetime, timezone
from typing import Optional, Union

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

    # Pattern to capture URLs, Discord mentions (<@123>, <#123>, <@&123>), and custom emojis (<:name:123>, <a:name:123>)
    token_pattern = re.compile(
        r'(https?://\S+|<@!?\d+>|<#\d+>|<@&\d+>|<a?:\w+:\d+>)'
    )

    parts = token_pattern.split(text)
    transformed_parts = []

    for idx, part in enumerate(parts):
        # Odd indices are matched protected tokens
        if idx % 2 == 1:
            transformed_parts.append(part)
        else:
            if not part:
                continue

            s = part
            # 1. Phonetic Replacements
            s = re.sub(r'r', 'w', s)
            s = re.sub(r'l', 'w', s)
            s = re.sub(r'R', 'W', s)
            s = re.sub(r'L', 'W', s)

            # 2. Nyification (n + vowel)
            s = re.sub(r'n([aeiou])', r'ny\1', s)
            s = re.sub(r'N([aeiou])', r'Ny\1', s)
            s = re.sub(r'N([AEIOU])', r'NY\1', s)

            # 3. Softening consonant clusters
            s = re.sub(r'\bthe\b', 'de', s, flags=re.IGNORECASE)
            s = re.sub(r'\bthis\b', 'dis', s, flags=re.IGNORECASE)
            s = re.sub(r'\bthat\b', 'dat', s, flags=re.IGNORECASE)
            s = re.sub(r'th', 'f', s)
            s = re.sub(r'TH', 'F', s)
            s = re.sub(r'ove', 'uv', s)

            # 4. Word Stuttering
            words = s.split(' ')
            stuttered_words = []
            for word in words:
                if len(word) >= 3 and word[0].isalpha() and random.random() < 0.35:
                    word = f"{word[0]}-{word}"
                stuttered_words.append(word)
            s = ' '.join(stuttered_words)

            # 5. Sentence kaomoji suffixes
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
    Restricted EXCLUSIVELY to Bot Owner and Trusted Bot Admins.
    """

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    # --- Storage Helpers (Upstash Redis + SQLite) ---

    async def _is_user_locked(self, guild_id: int, user_id: int) -> bool:
        """Check if user is NymLocked via Redis or SQLite fallback."""
        key = f"nymlock:{guild_id}:{user_id}"

        # 1. Redis check
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

        # 2. SQLite check
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

        # 1. SQLite
        await self.bot.db.execute(
            """
            INSERT INTO nymlock_users (guild_id, user_id, locked_by)
            VALUES (?, ?, ?)
            ON CONFLICT(guild_id, user_id) DO UPDATE SET locked_by = excluded.locked_by
            """,
            (guild_id, user_id, locked_by)
        )

        # 2. Redis
        if hasattr(self.bot, "upstash") and self.bot.upstash.is_configured:
            try:
                await self.bot.upstash.set(key, json.dumps(data))
                # Add to guild list cache
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

        # 1. SQLite
        await self.bot.db.execute(
            "DELETE FROM nymlock_users WHERE guild_id = ? AND user_id = ?",
            (guild_id, user_id)
        )

        # 2. Redis
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

    # --- Commands (Trusted Admins Only) ---

    @discord.slash_command(name="nymlock", description="[Trusted Admin Only] Lock a member into forced UwU speech mode.")
    async def nymlock_slash(self, ctx: discord.ApplicationContext, member: discord.Member):
        """Slash command for trusted admin speech lock."""
        if not await is_trusted_admin(ctx):
            embed = EmbedBuilder.error("Access Denied", "Only Bot Owner and Trusted Bot Admins can enforce NymLock.")
            return await ctx.respond(embed=embed, ephemeral=True)

        if member.id == ctx.guild.owner_id:
            embed = EmbedBuilder.error("Immunity Active", "The Guild Owner cannot be NymLocked.")
            return await ctx.respond(embed=embed, ephemeral=True)

        await self._set_user_lock(ctx.guild.id, member.id, ctx.author.id)

        embed = EmbedBuilder.base(
            title="✦ NymLock Enforced",
            description=f"✧ **Subject**: {member.mention} has been **NymLocked**!\n"
                        f"• **Enforcer**: {ctx.author.mention}\n"
                        f"• **Effect**: All speech in this server will be converted to UwU speak.",
            color=EmbedBuilder.COLOR_ERROR,
            author=ctx.author
        )
        await ctx.respond(embed=embed)

    @discord.slash_command(name="nymunlock", description="[Trusted Admin Only] Unlock a member from NymLock speech mode.")
    async def nymunlock_slash(self, ctx: discord.ApplicationContext, member: discord.Member):
        """Slash command for trusted admin speech unlock."""
        if not await is_trusted_admin(ctx):
            embed = EmbedBuilder.error("Access Denied", "Only Bot Owner and Trusted Bot Admins can lift NymLock.")
            return await ctx.respond(embed=embed, ephemeral=True)

        await self._delete_user_lock(ctx.guild.id, member.id)

        embed = EmbedBuilder.base(
            title="✧ NymLock Released",
            description=f"✧ **Subject**: {member.mention} speech lock has been **lifted**.\n"
                        f"• **Enforcer**: {ctx.author.mention}",
            color=EmbedBuilder.COLOR_SUCCESS,
            author=ctx.author
        )
        await ctx.respond(embed=embed)

    @discord.slash_command(name="nymlocklist", description="[Trusted Admin Only] List all NymLocked members in this server.")
    async def nymlocklist_slash(self, ctx: discord.ApplicationContext):
        """Slash command listing all NymLocked members."""
        if not await is_trusted_admin(ctx):
            embed = EmbedBuilder.error("Access Denied", "Only Bot Owner and Trusted Bot Admins can view NymLock list.")
            return await ctx.respond(embed=embed, ephemeral=True)

        user_ids = await self._get_locked_users(ctx.guild.id)

        if not user_ids:
            embed = EmbedBuilder.warning("No Locked Subjects", "No subjects are currently NymLocked in this server.")
            return await ctx.respond(embed=embed, ephemeral=True)

        mentions = [f"• {ctx.guild.get_member(uid).mention if ctx.guild.get_member(uid) else f'`ID: {uid}`'}" for uid in user_ids]

        embed = EmbedBuilder.base(
            title="📜 NymLocked Subjects",
            description="\n".join(mentions),
            color=EmbedBuilder.COLOR_NEKOTINA,
            author=ctx.author,
            footer=f"Total Locked: {len(mentions)}"
        )
        await ctx.respond(embed=embed)

    # --- Prefix Commands Fallback ---

    @commands.command(name="nymlock", aliases=["hl"])
    async def nymlock_prefix(self, ctx: commands.Context, member: discord.Member):
        """Prefix command fallback (!nymlock <@user> / nym nymlock <@user> / !hl <@user>)."""
        if not await is_trusted_admin(ctx):
            return await ctx.send("❌ **Access Denied**: Only Bot Owner and Trusted Bot Admins can enforce NymLock.")

        if member.id == ctx.guild.owner_id:
            return await ctx.send("⚠️ The Guild Owner cannot be NymLocked.")

        await self._set_user_lock(ctx.guild.id, member.id, ctx.author.id)
        embed = EmbedBuilder.base(
            title="✦ NymLock Enforced",
            description=f"✧ **Subject**: {member.mention} has been **NymLocked**!\n"
                        f"• **Enforcer**: {ctx.author.mention}\n"
                        f"• **Effect**: All speech in this server will be converted to UwU speak.",
            color=EmbedBuilder.COLOR_ERROR,
            author=ctx.author
        )
        await ctx.send(embed=embed)

    @commands.command(name="nymunlock", aliases=["hul"])
    async def nymunlock_prefix(self, ctx: commands.Context, member: discord.Member):
        """Prefix command fallback (!nymunlock <@user> / !hul <@user>)."""
        if not await is_trusted_admin(ctx):
            return await ctx.send("❌ **Access Denied**: Only Bot Owner and Trusted Bot Admins can lift NymLock.")

        await self._delete_user_lock(ctx.guild.id, member.id)
        embed = EmbedBuilder.base(
            title="✧ NymLock Released",
            description=f"✧ **Subject**: {member.mention} speech lock has been **lifted**.\n"
                        f"• **Enforcer**: {ctx.author.mention}",
            color=EmbedBuilder.COLOR_SUCCESS,
            author=ctx.author
        )
        await ctx.send(embed=embed)

    @commands.command(name="nymlocklist", aliases=["hll"])
    async def nymlocklist_prefix(self, ctx: commands.Context):
        """Prefix command fallback (!nymlocklist / !hll)."""
        if not await is_trusted_admin(ctx):
            return await ctx.send("❌ **Access Denied**: Only Bot Owner and Trusted Bot Admins can view NymLock list.")

        user_ids = await self._get_locked_users(ctx.guild.id)
        if not user_ids:
            return await ctx.send("⚠️ No subjects are currently NymLocked in this server.")

        mentions = [f"• {ctx.guild.get_member(uid).mention if ctx.guild.get_member(uid) else f'`ID: {uid}`'}" for uid in user_ids]
        embed = EmbedBuilder.base(
            title="📜 NymLocked Subjects",
            description="\n".join(mentions),
            color=EmbedBuilder.COLOR_NEKOTINA,
            author=ctx.author,
            footer=f"Total Locked: {len(mentions)}"
        )
        await ctx.send(embed=embed)


    # --- Event Listener for Speech Interception ---

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        """Intercepts messages sent by NymLocked members and transforms them."""
        if not message.guild or message.author.bot or not isinstance(message.channel, discord.TextChannel):
            return

        # Check if member is locked
        if not await self._is_user_locked(message.guild.id, message.author.id):
            return

        # 1. Delete original message
        try:
            await message.delete()
        except discord.Forbidden:
            return
        except Exception:
            pass

        # 2. Transform text
        converted_text = nym_uwuify(message.content) if message.content else random.choice(KAOMOJI_SUFFIXES).strip()

        # 3. Collect attachments
        files = []
        for att in message.attachments:
            try:
                files.append(await att.to_file())
            except Exception:
                pass

        # 4. Fetch or create Webhook for re-broadcasting
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
