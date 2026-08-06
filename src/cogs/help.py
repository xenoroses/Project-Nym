import discord
from discord.ext import commands
from src.utils.embeds import EmbedBuilder


class HelpCategorySelect(discord.ui.Select):
    """Nekotina-style Interactive Dropdown Menu for Help Categories."""

    def __init__(self, bot: commands.Bot, author_id: int):
        self.bot = bot
        self.author_id = author_id

        options = [
            discord.SelectOption(
                label="Main Overview",
                description="General bot statistics and quick start guide.",
                emoji="🏠",
                value="overview",
                default=True,
            ),
            discord.SelectOption(
                label="Prefix Management",
                description="Set, add, remove, or reset server prefixes.",
                emoji="⚙️",
                value="prefix",
            ),
            discord.SelectOption(
                label="Sticky Messages",
                description="Set and manage persistent sticky notices in channels.",
                emoji="📌",
                value="sticky",
            ),
            discord.SelectOption(
                label="AutoDelete Engine",
                description="Automatic message deletion by time intervals and filters.",
                emoji="🗑️",
                value="autodelete",
            ),
            discord.SelectOption(
                label="NymLock Engine",
                description="[Trusted Admin Only] Forced speech transformation into UwU speak.",
                emoji="🔒",
                value="nymlock",
            ),
            discord.SelectOption(
                label="System & Health",
                description="Check latency, uptime, and database operational status.",
                emoji="💚",
                value="health",
            ),
            discord.SelectOption(
                label="Developer & Eval",
                description="Owner code evaluation, AST returns, and script execution.",
                emoji="⚡",
                value="eval",
            ),
        ]


        super().__init__(placeholder="🌸 Choose a command category...", min_values=1, max_values=1, options=options)

    async def callback(self, interaction: discord.Interaction):
        if interaction.user.id != self.author_id:
            return await interaction.response.send_message(
                "❌ Only the command invoker can switch help pages.", ephemeral=True
            )

        category = self.values[0]

        # Reset defaults on options
        for option in self.options:
            option.default = (option.value == category)

        embed = self._build_category_embed(category, interaction.user)
        await interaction.response.edit_message(embed=embed, view=self.view)

    def _build_category_embed(self, category: str, user: discord.User) -> discord.Embed:
        bot_user = self.bot.user
        bot_avatar = bot_user.display_avatar.url if bot_user else None

        if category == "overview":
            embed = EmbedBuilder.base(
                title="✨ Nym — Command Hub & Assistance",
                description=(
                    "Welcome to **Nym**! A high-performance, modular Discord bot.\n"
                    "Use the dropdown menu below or click the category buttons to explore available commands.\n\n"
                    "**Quick Usage:**\n"
                    "• Slash commands: `/ping`, `/prefix set`, `/sticky`\n"
                    "• Prefix commands: `nym ping`, `!prefix set nym`, `,help`"
                ),
                color=EmbedBuilder.COLOR_NEKOTINA,
                author=user,
                thumbnail_url=bot_avatar,
            )
            embed.add_field(name="🌐 Operational Status", value="`24/7 Active Protocol` ✅", inline=True)
            embed.add_field(name="📊 Connected Servers", value=f"`{len(self.bot.guilds)}`", inline=True)
            embed.add_field(name="⚡ Active Commands", value=f"`{len(self.bot.commands)}`", inline=True)


        elif category == "prefix":
            embed = EmbedBuilder.base(
                title="⚙️ Prefix Management Commands",
                description="Configure custom server prefixes. Syncs with SQLite and Upstash Redis.",
                color=EmbedBuilder.COLOR_PRIMARY,
                author=user,
            )
            embed.add_field(name="`/prefix set <prefix>` / `nym prefix set`", value="Set primary server prefix (e.g. `nym`).", inline=False)
            embed.add_field(name="`/prefix add <prefix>` / `nym prefix add`", value="Add an additional command prefix.", inline=False)
            embed.add_field(name="`/prefix remove <prefix>` / `nym prefix remove`", value="Remove a custom prefix.", inline=False)
            embed.add_field(name="`/prefix reset` / `nym prefix reset`", value="Reset prefixes back to default (`!` and `,`).", inline=False)
            embed.add_field(name="`/prefix list` / `nym prefix`", value="Display all active prefixes for this server.", inline=False)

        elif category == "sticky":
            embed = EmbedBuilder.base(
                title="📌 Sticky Message Engine",
                description="Keep critical announcements permanently visible at the bottom of high-traffic channels.",
                color=EmbedBuilder.COLOR_NEKOTINA,
                author=user,
            )
            embed.add_field(name="`/sticky <message>` / `nym sticky`", value="Set a sticky notice for the current channel.", inline=False)
            embed.add_field(name="`/unsticky` / `nym unsticky`", value="Remove the active sticky notice from this channel.", inline=False)

        elif category == "autodelete":
            embed = EmbedBuilder.base(
                title="🗑️ AutoDelete Engine (EazyAutodelete)",
                description="Automatically clean up channel posts after custom durations (e.g. 5m, 1h, 24h, 1w) or content filters.",
                color=EmbedBuilder.COLOR_NEKOTINA,
                author=user,
            )
            embed.add_field(name="`/autodelete set <duration> [channel] [filter]`", value="Set autodelete interval and filter (e.g. `5m`, `1h`, `24h`, `0` for instant).", inline=False)
            embed.add_field(name="`/autodelete off [channel]`", value="Turn off autodelete in a channel.", inline=False)
            embed.add_field(name="`/autodelete status [channel]`", value="Check active autodelete configuration.", inline=False)
            embed.add_field(name="`!autodelete <duration>` / `nym autodelete <duration>`", value="Prefix command fallback for autodelete setup.", inline=False)

        elif category == "nymlock":
            embed = EmbedBuilder.base(
                title="🔒 NymLock Speech Engine",
                description="[Trusted Admin Only] Force a target member's speech into intense UwU speak via webhook impersonation.",
                color=EmbedBuilder.COLOR_ERROR,
                author=user,
            )
            embed.add_field(name="`/nymlock <@user>` / `!nymlock <@user>` / `!hl <@user>`", value="Lock a member into NymLock speech mode.", inline=False)
            embed.add_field(name="`/nymunlock <@user>` / `!nymunlock <@user>` / `!hul <@user>`", value="Unlock a member from NymLock speech mode.", inline=False)
            embed.add_field(name="`/nymlocklist` / `!nymlocklist` / `!hll`", value="List all currently locked members in this server.", inline=False)
            embed.add_field(name="🛡️ Access Control", value="Restricted strictly to Bot Owner & registered Bot Admins.", inline=False)



        elif category == "health":
            embed = EmbedBuilder.base(
                title="💚 System & Health Commands",
                description="Monitor bot latency, HTTP server endpoints, and database connection status.",
                color=EmbedBuilder.COLOR_SUCCESS,
                author=user,
            )
            embed.add_field(name="`/ping` / `nym ping`", value="Check websocket latency and API response time.", inline=False)
            embed.add_field(name="`/info` / `nym info`", value="Display Nym system architecture and environment info.", inline=False)
            embed.add_field(name="`/health` / `nym health`", value="Display full system health metrics and Upstash Redis ping.", inline=False)

        elif category == "eval":
            embed = EmbedBuilder.base(
                title="⚡ Developer Evaluation & Admin Engine",
                description="Owner & Trusted Admin code execution sandbox and access control management.",
                color=EmbedBuilder.COLOR_WARNING,
                author=user,
            )
            embed.add_field(name="`/eval <code>` / `nym eval <code>`", value="Evaluate Python code in Nym's async runtime.", inline=False)
            embed.add_field(name="`nym evalfile`", value="Attach a `.py` file to execute complex scripts.", inline=False)
            embed.add_field(name="`nym addadmin <@user>`", value="[Owner Only] Grant global Bot Admin & eval privileges.", inline=False)
            embed.add_field(name="`nym removeadmin <@user>`", value="[Owner Only] Revoke global Bot Admin privileges.", inline=False)
            embed.add_field(name="`nym listadmins`", value="List all registered Bot Admins with eval access.", inline=False)

        return embed



class NekotinaHelpView(discord.ui.View):
    """Nekotina-styled interactive UI View with Category Dropdown."""

    def __init__(self, bot: commands.Bot, author_id: int, timeout: float = 120.0):
        super().__init__(timeout=timeout)
        self.bot = bot
        self.author_id = author_id

        # Add Category Dropdown
        self.select = HelpCategorySelect(bot, author_id)
        self.add_item(self.select)


    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.author_id:
            await interaction.response.send_message("❌ Only the command invoker can use this menu.", ephemeral=True)
            return False
        return True

    @discord.ui.button(label="Home", style=discord.ButtonStyle.secondary, emoji="🏠", row=1)
    async def home_button(self, button: discord.ui.Button, interaction: discord.Interaction):
        # Reset select dropdown to Overview
        for option in self.select.options:
            option.default = (option.value == "overview")

        embed = self.select._build_category_embed("overview", interaction.user)
        await interaction.response.edit_message(embed=embed, view=self)


class HelpCog(commands.Cog):
    """Nekotina-style Custom Interactive Help Command."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.command(name="help")
    async def help_prefix(self, ctx: commands.Context):
        """Prefix command for interactive help (!help / nym help)."""
        view = NekotinaHelpView(self.bot, ctx.author.id)
        embed = view.select._build_category_embed("overview", ctx.author)
        await ctx.send(embed=embed, view=view)

    @discord.slash_command(name="help", description="Open Nym's interactive command menu.")
    async def help_slash(self, ctx: discord.ApplicationContext):
        """Slash command for interactive help (/help)."""
        view = NekotinaHelpView(self.bot, ctx.author.id)
        embed = view.select._build_category_embed("overview", ctx.author)
        await ctx.respond(embed=embed, view=view)

    @discord.slash_command(name="privacy", description="View Nym Bot's official Privacy Policy & Data Usage Terms.")
    async def privacy_command(self, ctx: discord.ApplicationContext):
        """Slash command displaying bot privacy policy and data usage terms."""
        embed = EmbedBuilder.info(
            title="🔒 Nym Privacy Policy & Data Usage",
            description=(
                "Nym respects your privacy and collects zero sensitive personal data.\n\n"
                "**Data Handling:**\n"
                "• **No Chat Logging:** Message contents are evaluated in-memory for commands/filters and never saved.\n"
                "• **Operational Settings Only:** Server command prefixes, sticky messages, and autodelete timers are stored in private databases.\n"
                "• **Zero Third-Party Sharing:** No data is sold, shared, or used for AI training.\n\n"
                "📄 **Official Privacy Policy:**\n"
                "https://github.com/xenoroses/Project-Nym/blob/main/PRIVACY_POLICY.md"
            ),
            footer="Nym Bot • Privacy & Security Standards",
        )
        await ctx.respond(embed=embed)

    @commands.command(name="privacy")
    async def privacy_prefix(self, ctx: commands.Context):
        """Prefix command fallback (!privacy / nym privacy)."""
        embed = EmbedBuilder.info(
            title="🔒 Nym Privacy Policy & Data Usage",
            description=(
                "Nym respects your privacy and collects zero sensitive personal data.\n\n"
                "**Data Handling:**\n"
                "• **No Chat Logging:** Message contents are evaluated in-memory for commands/filters and never saved.\n"
                "• **Operational Settings Only:** Server command prefixes, sticky messages, and autodelete timers are stored in private databases.\n"
                "• **Zero Third-Party Sharing:** No data is sold, shared, or used for AI training.\n\n"
                "📄 **Official Privacy Policy:**\n"
                "https://github.com/xenoroses/Project-Nym/blob/main/PRIVACY_POLICY.md"
            ),
            footer="Nym Bot • Privacy & Security Standards",
        )
        await ctx.send(embed=embed)


def setup(bot: commands.Bot):
    bot.add_cog(HelpCog(bot))
