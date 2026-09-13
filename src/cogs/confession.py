import json
import logging
from datetime import datetime, timezone
from typing import Optional, Union, List, Any

import discord
from discord.ext import commands
from src.utils.embeds import EmbedBuilder

logger = logging.getLogger("Nym")

IS_PYCORD = hasattr(discord, "SlashCommandGroup")
if not IS_PYCORD:
    from discord import app_commands


class ConfessionModal(discord.ui.Modal):
    """Interactive Modal for submitting anonymous confessions."""

    def __init__(self, bot: commands.Bot, cog: "ConfessionCog"):
        super().__init__(title="Anonymous Confession Portal")
        self.bot = bot
        self.cog = cog

        if IS_PYCORD:
            self.add_item(
                discord.ui.InputText(
                    label="Your Anonymous Confession",
                    style=discord.InputTextStyle.paragraph,
                    placeholder="Type your confession here... Your identity will remain hidden from server members.",
                    max_length=2000,
                    required=True,
                )
            )
        else:
            self.confession_input = discord.ui.TextInput(
                label="Your Anonymous Confession",
                style=discord.TextStyle.paragraph,
                placeholder="Type your confession here... Your identity will remain hidden from server members.",
                max_length=2000,
                required=True,
            )
            self.add_item(self.confession_input)

    async def callback(self, interaction: discord.Interaction):
        confession_text = ""
        if hasattr(self, "children") and self.children and hasattr(self.children[0], "value"):
            confession_text = str(self.children[0].value or "").strip()
        elif hasattr(self, "confession_input") and hasattr(self.confession_input, "value"):
            confession_text = str(self.confession_input.value or "").strip()

        if not confession_text:
            try:
                if hasattr(interaction, "response") and not interaction.response.is_done():
                    return await interaction.response.send_message(
                        "❌ Confession text cannot be empty.", ephemeral=True
                    )
            except Exception:
                pass
            return

        await self.cog.process_confession(
            interaction=interaction,
            user=interaction.user,
            guild=interaction.guild,
            content=confession_text,
        )

    async def on_submit(self, interaction: discord.Interaction):
        await self.callback(interaction)


class ConfessionPanelView(discord.ui.View):
    """Persistent UI View containing the 'Submit Confession' button."""

    def __init__(self, bot: commands.Bot, cog: Optional["ConfessionCog"] = None):
        super().__init__(timeout=None)
        self.bot = bot
        self.cog = cog

    @discord.ui.button(
        label="Submit Confession",
        style=discord.ButtonStyle.primary,
        emoji="✉️",
        custom_id="nym_confession_submit_btn",
    )
    async def submit_button(self, arg1: Any, arg2: Any):
        interaction = arg2 if isinstance(arg2, discord.Interaction) else arg1
        cog = self.bot.get_cog("ConfessionCog") or self.cog
        if not cog:
            try:
                if hasattr(interaction, "response") and not interaction.response.is_done():
                    return await interaction.response.send_message("❌ Confession engine is currently offline.", ephemeral=True)
            except Exception:
                pass
            return

        modal = ConfessionModal(self.bot, cog)
        try:
            if hasattr(interaction, "response") and hasattr(interaction.response, "send_modal"):
                await interaction.response.send_modal(modal)
            elif hasattr(interaction, "send_modal"):
                await interaction.send_modal(modal)
        except Exception as e:
            logger.error(f"Failed opening confession modal: {e}")


class ConfessionCog(commands.Cog):
    """Aesthetic Anonymous Confession Engine for Project Nym."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.config_cache = {}
        try:
            self.bot.add_view(ConfessionPanelView(bot, self))
        except Exception:
            pass

    @commands.Cog.listener()
    async def on_ready(self):
        """Pre-populate confession config RAM cache from SQLite DB and Upstash Redis on startup."""
        try:
            self.bot.add_view(ConfessionPanelView(self.bot, self))
        except Exception:
            pass

        try:
            rows = await self.bot.db.fetch_all("SELECT guild_id, channel_id, log_channel_id FROM confession_configs")
            if rows:
                for row in rows:
                    if row["guild_id"] and row["channel_id"]:
                        gid = int(row["guild_id"])
                        self.config_cache[gid] = {
                            "channel_id": int(row["channel_id"]),
                            "log_channel_id": int(row["log_channel_id"]) if row["log_channel_id"] else None,
                        }
        except Exception as e:
            logger.warning(f"SQLite confession config pre-population notice: {e}")

    def resolve_channel_id(self, ch: Any) -> Optional[int]:
        """Safely resolve channel ID from discord object, string mention, or integer."""
        if ch is None:
            return None
        if hasattr(ch, "id"):
            return ch.id
        if isinstance(ch, (int, str)):
            s = str(ch).strip("<#> ")
            if s.isdigit():
                return int(s)
        return None

    async def refresh_confession_panel(self, channel: discord.TextChannel):
        """Delete the old confession panel and repost it underneath the newest confession."""
        try:
            async for message in channel.history(limit=100):
                if message.author.id != self.bot.user.id:
                    continue

                if not message.embeds:
                    continue

                embed = message.embeds[0]

                if embed.title and "Anonymous Confession Portal" in embed.title:
                    await message.delete()
                    break

        except Exception as e:
            logger.warning(f"Failed deleting old confession panel: {e}")

        panel_embed = discord.Embed(
            title="💖 Anonymous Confession Portal",
            description="Click the button below to submit an **anonymous confession**.\n"
                        "Your identity will remain completely hidden from regular server members.",
            color=0xFF69B4,
        )

        view = ConfessionPanelView(self.bot, self)

        try:
            await channel.send(embed=panel_embed, view=view)
        except Exception as e:
            logger.warning(f"Failed reposting confession panel: {e}")

    # --- Storage Helpers ---

    async def _get_guild_config(self, guild_id: int) -> Optional[dict]:
        """Fetch confession configuration with RAM Cache -> SQLite DB -> Upstash Redis fallback."""
        if guild_id in self.config_cache:
            cached = self.config_cache[guild_id]
            if cached and cached.get("channel_id"):
                return cached

        # SQLite DB primary check
        try:
            row = await self.bot.db.fetch_one(
                "SELECT channel_id, log_channel_id FROM confession_configs WHERE guild_id = ?",
                (guild_id,),
            )
            if row and row["channel_id"]:
                data = {
                    "channel_id": int(row["channel_id"]),
                    "log_channel_id": int(row["log_channel_id"]) if row["log_channel_id"] else None,
                }
                self.config_cache[guild_id] = data
                return data
        except Exception as e:
            logger.error(f"SQLite read error for confession config {guild_id}: {e}")

        key = f"nym:confession:config:{guild_id}"
        legacy_key = f"confession:config:{guild_id}"

        if getattr(self.bot, "upstash", None) and self.bot.upstash.is_configured:
            try:
                raw_data = await self.bot.upstash.get(key) or await self.bot.upstash.get(legacy_key)
                if raw_data:
                    parsed = json.loads(raw_data)
                    if isinstance(parsed, str):
                        try: parsed = json.loads(parsed)
                        except Exception: pass
                    if isinstance(parsed, dict) and parsed.get("channel_id"):
                        self.config_cache[guild_id] = parsed
                        return parsed
            except Exception as e:
                logger.warning(f"Upstash read failed for confession config {guild_id}: {e}")

        return None

    async def _set_guild_config(
        self,
        guild_id: int,
        channel_id: Optional[int] = None,
        log_channel_id: Optional[int] = None,
    ) -> dict:
        """Save confession configuration for a guild to RAM Cache, SQLite DB, and Upstash Redis."""
        key = f"nym:confession:config:{guild_id}"
        legacy_key = f"confession:config:{guild_id}"

        current = await self._get_guild_config(guild_id) or {
            "channel_id": None,
            "log_channel_id": None,
        }

        if channel_id is not None:
            current["channel_id"] = channel_id
        if log_channel_id is not None:
            current["log_channel_id"] = log_channel_id

        self.config_cache[guild_id] = current

        try:
            await self.bot.db.execute(
                """
                INSERT INTO confession_configs (guild_id, channel_id, log_channel_id)
                VALUES (?, ?, ?)
                ON CONFLICT(guild_id) DO UPDATE SET
                    channel_id = excluded.channel_id,
                    log_channel_id = excluded.log_channel_id
                """,
                (
                    guild_id,
                    current["channel_id"],
                    current["log_channel_id"],
                ),
            )
        except Exception as e:
            logger.error(f"SQLite write error for confession config {guild_id}: {e}")

        if getattr(self.bot, "upstash", None) and self.bot.upstash.is_configured:
            try:
                payload = json.dumps(current)
                await self.bot.upstash.set(key, payload)
                await self.bot.upstash.set(legacy_key, payload)
            except Exception as e:
                logger.warning(f"Upstash set failed for confession config {guild_id}: {e}")

        return current

    # --- Core Confession Processor ---

    async def process_confession(
        self,
        interaction: Optional[discord.Interaction],
        user: Union[discord.User, discord.Member],
        guild: discord.Guild,
        content: str,
    ):
        """Processes and posts an anonymous confession and logs audit details for admins."""
        config = await self._get_guild_config(guild.id)
        if not config or not config.get("channel_id"):
            msg = "⚠️ Confession channel is not configured in this server. An admin must run `/confess setup` or `!confess setup #channel`."
            if interaction:
                return await interaction.response.send_message(msg, ephemeral=True)
            else:
                try:
                    return await user.send(msg)
                except Exception:
                    pass
            return

        confession_ch = guild.get_channel(config["channel_id"])
        if not confession_ch:
            msg = "❌ Configured confession channel was not found."
            if interaction:
                return await interaction.response.send_message(msg, ephemeral=True)
            else:
                try:
                    return await user.send(msg)
                except Exception:
                    pass
            return

        # 1. Post Anonymous Confession to Public Channel (Title-Less Quote Card, Pink Color)
        public_embed = discord.Embed(
            description=f">>> *“{content}”*",
            color=0xFF69B4,
        )

        try:
            await confession_ch.send(embed=public_embed)
            await self.refresh_confession_panel(confession_ch)
        except Exception as e:
            logger.error(f"Failed sending public confession in channel {confession_ch.id}: {e}")
            if interaction:
                return await interaction.response.send_message(
                    "❌ Failed to post confession to channel. Check bot permissions.",
                    ephemeral=True,
                )

        # 2. Post Private Audit Log to Admin Log Channel (If Configured)
        log_ch_id = config.get("log_channel_id")
        if log_ch_id:
            log_ch = guild.get_channel(log_ch_id)
            if log_ch:
                admin_embed = discord.Embed(
                    title="🕵️ Anonymous Confession Log",
                    description=f"**Content:**\n>>> {content}",
                    color=0xE74C3C,
                    timestamp=datetime.now(timezone.utc)
                )
                admin_embed.add_field(
                    name="👤 Author Identity",
                    value=f"{user.mention} (`{user}` | `ID: {user.id}`)",
                    inline=True,
                )
                admin_embed.add_field(
                    name="📍 Channel",
                    value=confession_ch.mention,
                    inline=True,
                )
                try:
                    await log_ch.send(embed=admin_embed)
                except Exception as e:
                    logger.warning(f"Failed sending admin audit log to channel {log_ch_id}: {e}")

        # Respond to sender ephemerally
        success_msg = "✨ Your anonymous confession has been submitted successfully."
        if interaction:
            if interaction.response.is_done():
                await interaction.followup.send(success_msg, ephemeral=True)
            else:
                await interaction.response.send_message(success_msg, ephemeral=True)
        else:
            try:
                await user.send(success_msg)
            except Exception:
                pass

    # --- Slash Commands Group ---

    if IS_PYCORD:
        confess = discord.SlashCommandGroup("confess", "Anonymous confession engine and administrator controls.")

        @confess.command(name="send", description="Submit an anonymous confession to the server confession channel.")
        async def confess_send_slash(self, ctx: discord.ApplicationContext, message: str = discord.Option(description="Your anonymous confession text")):
            await self.process_confession(interaction=ctx.interaction, user=ctx.author, guild=ctx.guild, content=message.strip())

        @confess.command(name="modal", description="Open multiline confession modal directly.")
        async def confess_modal_slash(self, ctx: discord.ApplicationContext):
            modal = ConfessionModal(self.bot, self)
            await ctx.send_modal(modal)

        @confess.command(name="setup", description="Set up designated channel for public anonymous confessions.")
        async def confess_setup_slash(
            self,
            ctx: discord.ApplicationContext,
            channel: discord.Option(description="Target channel for public confessions"),
            log_channel: discord.Option(description="Private admin channel for author audit logs (Optional)", default=None),
        ):
            if not ctx.author.guild_permissions.manage_channels and not ctx.author.guild_permissions.administrator:
                return await ctx.respond("❌ You need **Manage Channels** or **Administrator** permission.", ephemeral=True)

            ch_id = self.resolve_channel_id(channel)
            if not ch_id:
                return await ctx.respond("❌ Invalid confession channel specified.", ephemeral=True)

            target_ch = ctx.guild.get_channel(ch_id)
            if not target_ch:
                return await ctx.respond(f"❌ Channel with ID `{ch_id}` not found in this server.", ephemeral=True)

            log_id = self.resolve_channel_id(log_channel)
            log_ch = ctx.guild.get_channel(log_id) if log_id else None

            await self._set_guild_config(guild_id=ctx.guild.id, channel_id=target_ch.id, log_channel_id=log_ch.id if log_ch else None)

            panel_embed = discord.Embed(
                title="💖 Anonymous Confession Portal",
                description="Click the button below to submit an **anonymous confession**.\n"
                            "Your identity will remain completely hidden from regular server members.",
                color=0xFF69B4,
            )
            view = ConfessionPanelView(self.bot, self)

            try:
                await target_ch.send(embed=panel_embed, view=view)
                log_msg = f" and log channel to {log_ch.mention}" if log_ch else ""
                await ctx.respond(f"✨ **Confession channel set to {target_ch.mention}{log_msg}.**", ephemeral=True)
            except Exception as e:
                await ctx.respond(f"❌ Failed setting up channel: {e}", ephemeral=True)

        @confess.command(name="panel", description="Send an interactive 'Submit Confession' button panel to the channel.")
        async def confess_panel_slash(
            self,
            ctx: discord.ApplicationContext,
            channel: Optional[discord.TextChannel] = discord.Option(description="Target channel (Defaults to current channel)", default=None),
        ):
            if not ctx.author.guild_permissions.manage_channels and not ctx.author.guild_permissions.administrator:
                return await ctx.respond("❌ You need **Manage Channels** or **Administrator** permission.", ephemeral=True)

            target_ch = channel or ctx.channel
            embed = discord.Embed(
                title="💖 Anonymous Confession Portal",
                description="Click the button below to submit an **anonymous confession**.\n"
                            "Your identity will remain completely hidden from regular server members.",
                color=0xFF69B4,
            )
            view = ConfessionPanelView(self.bot, self)

            try:
                await target_ch.send(embed=embed, view=view)
                await ctx.respond(f"✅ Interactive confession panel posted to {target_ch.mention}.", ephemeral=True)
            except Exception as e:
                await ctx.respond(f"❌ Failed posting panel to {target_ch.mention}: {e}", ephemeral=True)

    else:
        confess_group = app_commands.Group(name="confess", description="Anonymous confession engine and administrator controls.")

        @confess_group.command(name="send", description="Submit an anonymous confession to the server confession channel.")
        async def confess_send_app(self, interaction: discord.Interaction, message: str):
            await self.process_confession(interaction=interaction, user=interaction.user, guild=interaction.guild, content=message.strip())

        @confess_group.command(name="modal", description="Open multiline confession modal directly.")
        async def confess_modal_app(self, interaction: discord.Interaction):
            modal = ConfessionModal(self.bot, self)
            await interaction.response.send_modal(modal)

        @confess_group.command(name="setup", description="Set up designated channel for public anonymous confessions.")
        @app_commands.checks.has_permissions(manage_channels=True)
        async def confess_setup_app(self, interaction: discord.Interaction, channel: discord.TextChannel, log_channel: Optional[discord.TextChannel] = None):
            log_id = log_channel.id if log_channel else None
            await self._set_guild_config(interaction.guild.id, channel_id=channel.id, log_channel_id=log_id)

            panel_embed = discord.Embed(
                title="💖 Anonymous Confession Portal",
                description="Click the button below to submit an **anonymous confession**.\n"
                            "Your identity will remain completely hidden from regular server members.",
                color=0xFF69B4,
            )
            view = ConfessionPanelView(self.bot, self)

            try:
                await channel.send(embed=panel_embed, view=view)
                log_msg = f" and log channel to {log_channel.mention}" if log_channel else ""
                await interaction.response.send_message(f"✨ **Confession channel set to {channel.mention}{log_msg}.**", ephemeral=True)
            except Exception as e:
                await interaction.response.send_message(f"❌ Failed setting up channel: {e}", ephemeral=True)

        @confess_group.command(name="panel", description="Send an interactive 'Submit Confession' button panel to the channel.")
        @app_commands.checks.has_permissions(manage_channels=True)
        async def confess_panel_app(self, interaction: discord.Interaction, channel: Optional[discord.TextChannel] = None):
            target_ch = channel or interaction.channel
            embed = discord.Embed(
                title="💖 Anonymous Confession Portal",
                description="Click the button below to submit an **anonymous confession**.\n"
                            "Your identity will remain completely hidden from regular server members.",
                color=0xFF69B4,
            )
            view = ConfessionPanelView(self.bot, self)

            try:
                await target_ch.send(embed=embed, view=view)
                await interaction.response.send_message(f"✅ Interactive confession panel posted to {target_ch.mention}.", ephemeral=True)
            except Exception as e:
                await interaction.response.send_message(f"❌ Failed posting panel to {target_ch.mention}: {e}", ephemeral=True)

    # --- Prefix Commands Fallback ---

    @commands.command(name="confess")
    async def confess_prefix(self, ctx: commands.Context, *, message: Optional[str] = None):
        """Prefix command fallback (!confess <message> / nym confess setup <#channel>)."""
        if not message:
            return await ctx.send("⚠️ Usage: `!confess <your confession>` or `/confess send`.")

        clean_text = message.strip()
        args = clean_text.split()
        sub = args[0].lower()

        if sub == "setup" and (ctx.author.guild_permissions.manage_channels or ctx.author.guild_permissions.administrator):
            if len(ctx.message.channel_mentions) > 0:
                ch = ctx.message.channel_mentions[0]
                log_ch = ctx.message.channel_mentions[1] if len(ctx.message.channel_mentions) > 1 else None
                log_id = log_ch.id if log_ch else None
                await self._set_guild_config(ctx.guild.id, channel_id=ch.id, log_channel_id=log_id)
                return await ctx.send(f"✧ Confession channel set to {ch.mention}.")
            return await ctx.send("⚠️ Please mention a channel: `!confess setup #confessions [#admin-log]`.")

        if sub == "panel" and (ctx.author.guild_permissions.manage_channels or ctx.author.guild_permissions.administrator):
            embed = discord.Embed(
                title="💖 Anonymous Confession Portal",
                description="Click the button below to submit an **anonymous confession**.\n"
                            "Your identity will remain completely hidden from regular server members.",
                color=0xFF69B4,
            )
            view = ConfessionPanelView(self.bot, self)
            await ctx.channel.send(embed=embed, view=view)
            try:
                await ctx.message.delete()
            except Exception:
                pass
            return

        if sub == "modal":
            modal = ConfessionModal(self.bot, self)
            if hasattr(ctx, "send_modal"):
                return await ctx.send_modal(modal)
            return await ctx.send("⚠️ Please use `/confess modal` or click the button on the confession portal panel.")

        # Delete author prefix message to preserve anonymity
        try:
            await ctx.message.delete()
        except Exception:
            pass

        await self.process_confession(
            interaction=None,
            user=ctx.author,
            guild=ctx.guild,
            content=clean_text,
        )


if IS_PYCORD:
    def setup(bot: commands.Bot):
        bot.add_cog(ConfessionCog(bot))
else:
    async def setup(bot: commands.Bot):
        await bot.add_cog(ConfessionCog(bot))
