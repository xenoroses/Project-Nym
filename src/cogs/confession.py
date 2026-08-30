import json
import logging
from datetime import datetime, timezone
from typing import Optional, Union, List, Any

import discord
from discord.ext import commands
from src.utils.embeds import EmbedBuilder

logger = logging.getLogger("Nym")


class ConfessionModal(discord.ui.Modal):
    """Interactive Modal for submitting anonymous confessions."""

    def __init__(self, bot: commands.Bot, cog: "ConfessionCog"):
        super().__init__(title="Anonymous Confession Portal")
        self.bot = bot
        self.cog = cog

        self.add_item(
            discord.ui.InputText(
                label="Your Anonymous Confession",
                style=discord.InputTextStyle.paragraph,
                placeholder="Type your confession here... Your identity will remain hidden from server members.",
                max_length=2000,
                required=True,
            )
        )

    async def callback(self, interaction: discord.Interaction):
        confession_text = self.children[0].value.strip()
        if not confession_text:
            return await interaction.response.send_message(
                "❌ Confession text cannot be empty.", ephemeral=True
            )

        await self.cog.process_confession(
            interaction=interaction,
            user=interaction.user,
            guild=interaction.guild,
            content=confession_text,
        )


class ConfessionPanelView(discord.ui.View):
    """Persistent UI View containing the 'Submit Confession' button."""

    def __init__(self, bot: commands.Bot, cog: Optional["ConfessionCog"] = None):
        super().__init__(timeout=None)
        self.bot = bot
        self.cog = cog

    @discord.ui.button(
        label="Submit Confession",
        style=discord.ButtonStyle.primary,
        custom_id="nym_confession_submit_btn",
    )
    async def submit_button(
        self, button: discord.ui.Button, interaction: discord.Interaction
    ):
        cog = self.bot.get_cog("ConfessionCog") or self.cog
        if not cog:
            return await interaction.response.send_message("❌ Confession engine is currently offline.", ephemeral=True)

        modal = ConfessionModal(self.bot, cog)
        await interaction.response.send_modal(modal)


class ConfessionCog(commands.Cog):
    """Aesthetic Anonymous Confession Engine for Project Nym."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.bot.add_view(ConfessionPanelView(bot, self))

    @commands.Cog.listener()
    async def on_ready(self):
        """Ensure persistent views are bound on bot ready."""
        self.bot.add_view(ConfessionPanelView(self.bot, self))

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

                if embed.title in (
                    "💖 Anonymous Confession Portal",
                    "🌸 Anonymous Confession Portal",
                ):
                    await message.delete()
                    break

        except Exception as e:
            logger.warning(f"Failed deleting old confession panel: {e}")

        panel_embed = EmbedBuilder.base(
            title="💖 Anonymous Confession Portal",
            description="Click the button below to submit an anonymous confession.\n"
                        "Your identity will remain completely hidden from server members.",
            color=EmbedBuilder.COLOR_NEKOTINA,
        )

        view = ConfessionPanelView(self.bot, self)

        try:
            await channel.send(embed=panel_embed, view=view)
        except Exception as e:
            logger.warning(f"Failed reposting confession panel: {e}")

    # --- Storage Helpers ---

    async def _get_guild_config(self, guild_id: int) -> Optional[dict]:
        """Fetch confession configuration for a guild."""
        key = f"confession:config:{guild_id}"

        if hasattr(self.bot, "upstash") and self.bot.upstash.is_configured:
            try:
                raw_data = await self.bot.upstash.get(key)
                if raw_data:
                    parsed = json.loads(raw_data)
                    if isinstance(parsed, dict):
                        return parsed
            except Exception as e:
                logger.warning(f"Upstash read failed for confession config {guild_id}: {e}")

        try:
            row = await self.bot.db.fetch_one(
                "SELECT channel_id, log_channel_id FROM confession_configs WHERE guild_id = ?",
                (guild_id,),
            )
            if row:
                data = {
                    "channel_id": row["channel_id"],
                    "log_channel_id": row["log_channel_id"],
                }
                if hasattr(self.bot, "upstash") and self.bot.upstash.is_configured:
                    await self.bot.upstash.set(key, json.dumps(data))
                return data
        except Exception as e:
            logger.error(f"SQLite read error for confession config {guild_id}: {e}")

        return None

    async def _set_guild_config(
        self,
        guild_id: int,
        channel_id: Optional[int] = None,
        log_channel_id: Optional[int] = None,
    ) -> dict:
        """Save confession configuration for a guild."""
        key = f"confession:config:{guild_id}"
        current = await self._get_guild_config(guild_id) or {
            "channel_id": None,
            "log_channel_id": None,
        }

        if channel_id is not None:
            current["channel_id"] = channel_id
        if log_channel_id is not None:
            current["log_channel_id"] = log_channel_id

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

        if hasattr(self.bot, "upstash") and self.bot.upstash.is_configured:
            try:
                await self.bot.upstash.set(key, json.dumps(current))
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
            msg = "⚠️ Confession channel is not configured in this server. An admin must run `/confess setup`."
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

        # 1. Post Anonymous Confession to Public Channel (No Counter / ID)
        public_embed = EmbedBuilder.base(
            title="💖 Anonymous Confession",
            description=content,
            color=EmbedBuilder.COLOR_NEKOTINA,
            include_timestamp=False,
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

        # 2. Post Private Audit Log to Admin Log Channel (If Configured, No ID / Counter)
        log_ch_id = config.get("log_channel_id")
        if log_ch_id:
            log_ch = guild.get_channel(log_ch_id)
            if log_ch:
                admin_embed = EmbedBuilder.base(
                    title="🕵️ Anonymous Confession Log",
                    description=f"**Content:**\n>>> {content}",
                    color=EmbedBuilder.COLOR_WARNING,
                    footer=f"Logged at {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S')} UTC",
                )
                admin_embed.add_field(
                    name="Author Identity",
                    value=f"{user.mention} (`{user.name}` | `ID: {user.id}`)",
                    inline=True,
                )
                admin_embed.add_field(
                    name="Channel",
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

    # --- Commands ---

    confess = discord.SlashCommandGroup(
        "confess", "Anonymous confession engine and administrator controls."
    )

    @confess.command(
        name="send",
        description="Submit an anonymous confession to the server confession channel.",
    )
    async def confess_send(
        self,
        ctx: discord.ApplicationContext,
        message: str = discord.Option(description="Your anonymous confession text"),
    ):
        """Submit an anonymous confession via slash command."""
        await self.process_confession(
            interaction=ctx.interaction,
            user=ctx.author,
            guild=ctx.guild,
            content=message.strip(),
        )

    @confess.command(
        name="setup", description="Set up the designated channel for public anonymous confessions."
    )
    async def confess_setup(
        self,
        ctx: discord.ApplicationContext,
        channel: discord.Option(description="Target channel for public confessions"), # type: ignore
        log_channel: discord.Option(description="Private admin channel for author audit logs (Optional)", default=None), # type: ignore
    ):
        """Configure public confession and private admin log channels."""
        if not ctx.author.guild_permissions.manage_channels and not ctx.author.guild_permissions.administrator:
            return await ctx.respond("❌ You need **Manage Channels** or **Administrator** permission to configure confessions.", ephemeral=True)

        ch_id = self.resolve_channel_id(channel)
        if not ch_id:
            return await ctx.respond("❌ Invalid confession channel specified.", ephemeral=True)

        target_ch = ctx.guild.get_channel(ch_id)
        if not target_ch:
            return await ctx.respond(f"❌ Channel with ID `{ch_id}` not found in this server.", ephemeral=True)

        log_id = self.resolve_channel_id(log_channel)
        log_ch = ctx.guild.get_channel(log_id) if log_id else None

        await self._set_guild_config(
            guild_id=ctx.guild.id, channel_id=target_ch.id, log_channel_id=log_ch.id if log_ch else None
        )

        embed = EmbedBuilder.success(
            title="Confession Engine Configured",
            description=f"✧ Public confessions channel set to {target_ch.mention}.\n"
                        f"• **Admin Audit Logs:** {log_ch.mention if log_ch else '`Not Configured`'}\n"
                        f"• Use `/confess panel` to send an interactive submission button to the channel.",
        )
        await ctx.respond(embed=embed, ephemeral=True)

    @confess.command(
        name="panel",
        description="Send an interactive 'Submit Confession' button panel to the channel.",
    )
    async def confess_panel(
        self,
        ctx: discord.ApplicationContext,
        channel: Optional[discord.TextChannel] = discord.Option(
            description="Target channel (Defaults to current channel)", default=None
        ),
    ):
        """Send an interactive submission panel with a modal popup button."""
        if not ctx.author.guild_permissions.manage_channels and not ctx.author.guild_permissions.administrator:
            return await ctx.respond("❌ You need **Manage Channels** or **Administrator** permission to post the panel.", ephemeral=True)

        target_ch = channel or ctx.channel
        embed = EmbedBuilder.base(
            title="💖 Anonymous Confession Portal",
            description="Click the button below to submit an **anonymous confession**.\n"
                        "Your identity will remain completely hidden from regular server members.",
            color=EmbedBuilder.COLOR_NEKOTINA,
        )
        view = ConfessionPanelView(self.bot, self)

        try:
            await target_ch.send(embed=embed, view=view)
            await ctx.respond(
                f"✅ Interactive confession panel posted to {target_ch.mention}.",
                ephemeral=True,
            )
        except Exception as e:
            await ctx.respond(
                f"❌ Failed posting panel to {target_ch.mention}: {e}", ephemeral=True
            )

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
            embed = EmbedBuilder.base(
                title="🌸 Anonymous Confession Portal",
                description="Click the button below to submit an anonymous confession.\n"
                            "Your identity will remain completely hidden from server members.",
                color=EmbedBuilder.COLOR_NEKOTINA,
            )
            view = ConfessionPanelView(self.bot, self)
            await ctx.channel.send(embed=embed, view=view)
            try:
                await ctx.message.delete()
            except Exception:
                pass
            return

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


def setup(bot: commands.Bot):
    bot.add_cog(ConfessionCog(bot))
