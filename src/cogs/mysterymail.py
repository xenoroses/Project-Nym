import discord
from discord.ext import commands
import uuid
import json
import os
from datetime import datetime, timezone

NYM_BANNER_PATH = "assets/banner.jpg"
NYM_BANNER_CDN = "https://cdn.discordapp.com/attachments/1000000000000000000/banner_lovesknot.jpg"

BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DATA_DIR = os.path.join(BASE_DIR, "data")
STORE_FILE = os.path.join(DATA_DIR, "nym_store.json")
_NYM_MEMORY_STORE = {}

def _load_nym_store():
    global _NYM_MEMORY_STORE
    try:
        if not os.path.exists(DATA_DIR):
            os.makedirs(DATA_DIR, exist_ok=True)
        if os.path.exists(STORE_FILE):
            with open(STORE_FILE, "r", encoding="utf-8") as f:
                _NYM_MEMORY_STORE = json.load(f)
    except Exception as e:
        _NYM_MEMORY_STORE = {}

def _save_nym_store():
    try:
        if not os.path.exists(DATA_DIR):
            os.makedirs(DATA_DIR, exist_ok=True)
        with open(STORE_FILE, "w", encoding="utf-8") as f:
            json.dump(_NYM_MEMORY_STORE, f, indent=2)
    except Exception:
        pass

_load_nym_store()

class NymMysteryMailModal(discord.ui.Modal):
    def __init__(self, target_user: discord.User):
        super().__init__(title="Send Mystery Mail")
        self.target_user = target_user
        self.add_item(
            discord.ui.InputText(
                label="Anonymous Message",
                style=discord.InputTextStyle.long,
                placeholder="Type your secret compliment, confession, or joke here...",
                required=True,
                max_length=1000
            )
        )

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        message_text = self.children[0].value.strip()

        # Check DND
        if _NYM_MEMORY_STORE.get(f"mysterymail_dnd:{self.target_user.id}"):
            return await interaction.followup.send(
                "⛔ **This member has enabled Do Not Disturb and is not accepting Mystery Mail.**",
                ephemeral=True
            )

        mail_id = str(uuid.uuid4())[:8]

        dm_embed = discord.Embed(
            title="💌 You received an anonymous message",
            description=f"{message_text}\n\n**Use the button below if you want to request the sender to reveal themselves.**",
            color=0xFF69B4
        )

        view = NymRevealRequestView(mail_id=mail_id)

        try:
            target_dm = await self.target_user.create_dm()
            await target_dm.send(embed=dm_embed, view=view)
        except discord.Forbidden:
            return await interaction.followup.send(
                "❌ **Unable to send DM to this user.** Their DMs may be closed or they have blocked the bot.",
                ephemeral=True
            )
        except Exception as e:
            return await interaction.followup.send(
                f"❌ **Failed to deliver Mystery Mail:** {e}",
                ephemeral=True
            )

        _NYM_MEMORY_STORE[f"mysterymail:{mail_id}"] = {
            "mail_id": mail_id,
            "sender_id": interaction.user.id,
            "target_id": self.target_user.id,
            "message": message_text,
            "revealed": False
        }
        _save_nym_store()

        # --- Audit Logging (Anti-Abuse Oversight) ---
        if interaction.guild:
            log_channel_id = _NYM_MEMORY_STORE.get(f"mysterymail_log_channel:{interaction.guild.id}")
            if log_channel_id:
                try:
                    log_channel = interaction.guild.get_channel(int(log_channel_id))
                    if log_channel:
                        audit_embed = discord.Embed(
                            title="💌 Mystery Mail Audit Log",
                            color=0xFF69B4,
                            timestamp=datetime.now(timezone.utc)
                        )
                        audit_embed.add_field(name="Sender", value=f"{interaction.user.mention} (`{interaction.user.id}`)", inline=True)
                        audit_embed.add_field(name="Recipient", value=f"{self.target_user.mention} (`{self.target_user.id}`)", inline=True)
                        audit_embed.add_field(name="Message", value=f"```\n{message_text}\n```", inline=False)
                        audit_embed.set_footer(text="Mystery Mail Anti-Abuse System")
                        await log_channel.send(embed=audit_embed)
                except Exception as e:
                    print(f"Nym Mystery Mail Audit Log Error: {e}")

        await interaction.followup.send(
            f"✨ **Mystery Mail delivered to {self.target_user.mention}!** Your identity remains 100% anonymous.",
            ephemeral=True
        )


class NymTargetSelectView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=120)

    @discord.ui.select(
        select_type=discord.ComponentType.user_select,
        placeholder="Select the recipient for your Mystery Mail...",
        min_values=1,
        max_values=1
    )
    async def select_target(self, select: discord.ui.Select, interaction: discord.Interaction):
        target = select.values[0]

        if target.bot:
            return await interaction.response.send_message(
                "❌ **You cannot send Mystery Mail to a bot.**",
                ephemeral=True
            )

        if target.id == interaction.user.id:
            return await interaction.response.send_message(
                "❌ **You cannot send Mystery Mail to yourself.**",
                ephemeral=True
            )

        if _NYM_MEMORY_STORE.get(f"mysterymail_dnd:{target.id}"):
            return await interaction.response.send_message(
                "⛔ **This member has enabled Do Not Disturb and is not accepting Mystery Mail.**",
                ephemeral=True
            )

        modal = NymMysteryMailModal(target_user=target)
        await interaction.response.send_modal(modal)


class NymRevealRequestView(discord.ui.View):
    def __init__(self, mail_id: str):
        super().__init__(timeout=None)
        self.mail_id = mail_id

    @discord.ui.button(label="Request to Reveal", style=discord.ButtonStyle.secondary, custom_id="nym_mm_btn_request_reveal")
    async def request_reveal(self, button: discord.ui.Button, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)

        mail_data = _NYM_MEMORY_STORE.get(f"mysterymail:{self.mail_id}")
        if not mail_data:
            return await interaction.followup.send("❌ This Mystery Mail record is no longer active.", ephemeral=True)

        if mail_data.get("revealed"):
            return await interaction.followup.send("✨ The sender has already revealed their identity!", ephemeral=True)

        sender_id = mail_data.get("sender_id")
        sender = interaction.client.get_user(sender_id) or await interaction.client.fetch_user(sender_id)

        if not sender:
            return await interaction.followup.send("❌ Unable to reach the sender.", ephemeral=True)

        sender_decision_embed = discord.Embed(
            title="📩 Identity Reveal Requested!",
            description=(
                f"{interaction.user.mention} received your Mystery Mail:\n"
                f"> *\"{mail_data.get('message')}\"*\n\n"
                "**They are asking to reveal your identity. Would you like to accept?**"
            ),
            color=0xFF69B4
        )

        decision_view = NymSenderDecisionView(mail_id=self.mail_id, recipient_id=interaction.user.id)

        try:
            sender_dm = await sender.create_dm()
            await sender_dm.send(embed=sender_decision_embed, view=decision_view)
            await interaction.followup.send(
                "✨ **Reveal request sent to the sender!** You will be notified if they accept.",
                ephemeral=True
            )
        except Exception:
            await interaction.followup.send(
                "❌ Could not deliver reveal request to sender (DMs closed).",
                ephemeral=True
            )


class NymSenderDecisionView(discord.ui.View):
    def __init__(self, mail_id: str, recipient_id: int):
        super().__init__(timeout=None)
        self.mail_id = mail_id
        self.recipient_id = recipient_id

    @discord.ui.button(label="Accept & Reveal Identity", style=discord.ButtonStyle.success, custom_id="nym_mm_btn_accept_reveal")
    async def accept_reveal(self, button: discord.ui.Button, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)

        mail_data = _NYM_MEMORY_STORE.get(f"mysterymail:{self.mail_id}")
        if not mail_data:
            return await interaction.followup.send("❌ Mystery Mail record not found.", ephemeral=True)

        mail_data["revealed"] = True

        recipient = interaction.client.get_user(self.recipient_id) or await interaction.client.fetch_user(self.recipient_id)

        if recipient:
            revealed_embed = discord.Embed(
                title="💖 Sender Revealed",
                description=(
                    f"This person sent that message to you: {interaction.user.mention}\n\n"
                    f"**Original message**\n{mail_data.get('message')}"
                ),
                color=0xFF69B4
            )
            try:
                recipient_dm = await recipient.create_dm()
                await recipient_dm.send(embed=revealed_embed)
            except: pass

        for child in self.children:
            child.disabled = True
        await interaction.message.edit(view=self)

        await interaction.followup.send(
            f"💖 **Identity revealed!** {recipient.mention if recipient else 'The recipient'} can now see who sent the message.",
            ephemeral=True
        )

    @discord.ui.button(label="Keep Anonymous", style=discord.ButtonStyle.danger, custom_id="nym_mm_btn_deny_reveal")
    async def deny_reveal(self, button: discord.ui.Button, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)

        recipient = interaction.client.get_user(self.recipient_id) or await interaction.client.fetch_user(self.recipient_id)

        if recipient:
            try:
                recipient_dm = await recipient.create_dm()
                await recipient_dm.send("🔒 **The sender chose to remain anonymous.**")
            except: pass

        for child in self.children:
            child.disabled = True
        await interaction.message.edit(view=self)

        await interaction.followup.send(
            "🔒 **You chose to stay anonymous.**",
            ephemeral=True
        )


class NymMysteryMailPanelView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Send Mystery Mail", style=discord.ButtonStyle.secondary, custom_id="nym_mm_panel_send_mail")
    async def send_mail_btn(self, button: discord.ui.Button, interaction: discord.Interaction):
        view = NymTargetSelectView()
        await interaction.response.send_message(
            "💌 Select who you want to send an anonymous Mystery Mail to:",
            view=view,
            ephemeral=True
        )

    @discord.ui.button(label="Toggle Do Not Disturb", style=discord.ButtonStyle.danger, custom_id="nym_mm_panel_toggle_dnd")
    async def toggle_dnd_btn(self, button: discord.ui.Button, interaction: discord.Interaction):
        key = f"mysterymail_dnd:{interaction.user.id}"
        current = _NYM_MEMORY_STORE.get(key)

        if current:
            _NYM_MEMORY_STORE.pop(key, None)
            _save_nym_store()
            await interaction.response.send_message(
                "✅ **You have disabled Do Not Disturb for Mystery Mail.** You can now receive anonymous messages.",
                ephemeral=True
            )
        else:
            _NYM_MEMORY_STORE[key] = True
            _save_nym_store()
            await interaction.response.send_message(
                "⛔ **You have enabled Do Not Disturb for Mystery Mail.** You will no longer receive anonymous messages.",
                ephemeral=True
            )


class MysteryMailCog(commands.Cog):
    """Mystery Mail Anonymous Messaging Engine for Nym."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.bot.add_view(NymMysteryMailPanelView())

    @discord.slash_command(name="mysterymail", description="Display the interactive Mystery Mail panel.")
    @commands.has_permissions(manage_guild=True)
    async def mysterymail_cmd(self, ctx: discord.ApplicationContext):
        embed = discord.Embed(
            description=(
                "*Ever wondered who's been thinking about you?*\n\n"
                "**Receive anonymous messages from other members and try to figure out who sent them. "
                "Whether it's a compliment, a confession, a joke, or just someone wanting to make you smile, "
                "every message is delivered privately by the bot.**\n\n"
                "✨ **__How it works__**\n\n"
                "♡ Receive anonymous messages in your DMs.\n"
                "♡ Decide if you want to guess who sent it.\n"
                "♡ Keep everyone guessing while staying anonymous.\n\n"
                "*Sometimes the sweetest messages come from the biggest mysteries. 💋*\n\n"
                "━━━━━━━ ✦ ━━━━━━━"
            ),
            color=0xFF69B4
        )

        view = NymMysteryMailPanelView()

        if os.path.exists(NYM_BANNER_PATH):
            file = discord.File(NYM_BANNER_PATH, filename="banner.jpg")
            embed.set_image(url="attachment://banner.jpg")
            await ctx.respond(embed=embed, file=file, view=view)
        else:
            embed.set_image(url=NYM_BANNER_CDN)
            await ctx.respond(embed=embed, view=view)

    @discord.slash_command(name="mysterymaillog", description="Set the audit log channel for Mystery Mail anti-abuse oversight.")
    @commands.has_permissions(manage_guild=True)
    async def mysterymaillog_cmd(self, ctx: discord.ApplicationContext, channel: discord.TextChannel):
        _NYM_MEMORY_STORE[f"mysterymail_log_channel:{ctx.guild.id}"] = str(channel.id)
        _save_nym_store()
        await ctx.respond(
            f"✅ **Mystery Mail audit log channel updated to {channel.mention}.** All sent anonymous messages will be logged here for admin oversight.",
            ephemeral=True
        )

    @discord.slash_command(name="mysterymaillogclear", description="Disable Mystery Mail audit logging.")
    @commands.has_permissions(manage_guild=True)
    async def mysterymaillogclear_cmd(self, ctx: discord.ApplicationContext):
        _NYM_MEMORY_STORE.pop(f"mysterymail_log_channel:{ctx.guild.id}", None)
        _save_nym_store()
        await ctx.respond(
            "🗑️ **Mystery Mail audit logging disabled for this server.**",
            ephemeral=True
        )


def setup(bot: commands.Bot):
    bot.add_cog(MysteryMailCog(bot))
