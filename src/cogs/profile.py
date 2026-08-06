import asyncio
import json
import logging
from datetime import datetime, timezone
from typing import Optional, Union, List

import discord
from discord.ext import commands
from src.utils.embeds import EmbedBuilder

logger = logging.getLogger("Nym")


class ProfileModal(discord.ui.Modal):
    """Interactive Modal for creating or editing a Server Dating Profile."""

    def __init__(self, bot: commands.Bot, cog: "DatingProfileCog", existing_data: Optional[dict] = None):
        title = "Edit Dating Profile" if existing_data else "Create Dating Profile"
        super().__init__(title=title)
        self.bot = bot
        self.cog = cog
        self.existing_data = existing_data or {}

        self.add_item(
            discord.ui.InputText(
                label="Age, Gender & Pronouns",
                placeholder="e.g. 21 | Female | She/Her",
                value=self.existing_data.get("age_gender") or "",
                max_length=100,
                required=True,
            )
        )
        self.add_item(
            discord.ui.InputText(
                label="Relationship Status & Looking For",
                placeholder="e.g. Single | Looking for Chat / Connections",
                value=self.existing_data.get("relationship_status") or "",
                max_length=100,
                required=True,
            )
        )
        self.add_item(
            discord.ui.InputText(
                label="Interests, Games & Hobbies",
                placeholder="e.g. WuWa, Valorant, Anime, Lofi Music, Reading",
                value=self.existing_data.get("interests") or "",
                max_length=200,
                required=True,
            )
        )
        self.add_item(
            discord.ui.InputText(
                label="About Me (Bio)",
                style=discord.InputTextStyle.paragraph,
                placeholder="Introduce yourself! What makes you unique?",
                value=self.existing_data.get("bio") or "",
                max_length=1000,
                required=True,
            )
        )
        self.add_item(
            discord.ui.InputText(
                label="Custom Banner Image / GIF URL (Optional)",
                placeholder="https://example.com/my-banner.gif",
                value=self.existing_data.get("image_url") or "",
                max_length=300,
                required=False,
            )
        )


    async def callback(self, interaction: discord.Interaction):
        age_gender = self.children[0].value.strip()
        status_looking = self.children[1].value.strip()
        interests = self.children[2].value.strip()
        bio = self.children[3].value.strip()
        image_url = self.children[4].value.strip() if len(self.children) > 4 and self.children[4].value else None

        await self.cog.save_user_profile(
            interaction=interaction,
            user=interaction.user,
            guild=interaction.guild,
            age_gender=age_gender,
            status_looking=status_looking,
            interests=interests,
            bio=bio,
            image_url=image_url,
        )


class DeleteConfirmView(discord.ui.View):
    """Confirmation View for profile deletion."""

    def __init__(self, bot: commands.Bot, cog: "DatingProfileCog", user_id: int):
        super().__init__(timeout=60)
        self.bot = bot
        self.cog = cog
        self.user_id = user_id

    @discord.ui.button(label="Confirm Delete", style=discord.ButtonStyle.danger, emoji="⚠️")
    async def confirm_btn(self, button: discord.ui.Button, interaction: discord.Interaction):
        if interaction.user.id != self.user_id:
            return await interaction.response.send_message("❌ You can only delete your own profile.", ephemeral=True)

        await self.cog.delete_user_profile(interaction, interaction.user)

    @discord.ui.button(label="Cancel", style=discord.ButtonStyle.secondary, emoji="✖️")
    async def cancel_btn(self, button: discord.ui.Button, interaction: discord.Interaction):
        if interaction.user.id != self.user_id:
            return await interaction.response.send_message("❌ Cancel action unavailable.", ephemeral=True)

        await interaction.response.edit_message(content="✨ Profile deletion cancelled.", embed=None, view=None)


class DatingProfilePanelView(discord.ui.View):
    """Main Persistent Panel UI View with Create, Edit, View, and Delete buttons."""

    def __init__(self, bot: commands.Bot, cog: Optional["DatingProfileCog"] = None):
        super().__init__(timeout=None)
        self.bot = bot
        self.cog = cog

    @discord.ui.button(
        label="Create Profile",
        style=discord.ButtonStyle.secondary,
        custom_id="nym_profile_create_btn",
    )
    async def create_button(self, button: discord.ui.Button, interaction: discord.Interaction):
        cog = self.bot.get_cog("DatingProfileCog") or self.cog
        if not cog:
            return await interaction.response.send_message("❌ Profile engine is currently offline.", ephemeral=True)

        modal = ProfileModal(self.bot, cog, existing_data=None)
        await interaction.response.send_modal(modal)

    @discord.ui.button(
        label="Edit Profile",
        style=discord.ButtonStyle.secondary,
        custom_id="nym_profile_edit_btn",
    )
    async def edit_button(self, button: discord.ui.Button, interaction: discord.Interaction):
        cog = self.bot.get_cog("DatingProfileCog") or self.cog
        if not cog:
            return await interaction.response.send_message("❌ Profile engine is currently offline.", ephemeral=True)

        try:
            profile = await asyncio.wait_for(cog.get_user_profile(interaction.user.id), timeout=1.0)
        except Exception:
            profile = None

        modal = ProfileModal(self.bot, cog, existing_data=profile)
        await interaction.response.send_modal(modal)

    @discord.ui.button(
        label="View My Profile Info",
        style=discord.ButtonStyle.secondary,
        custom_id="nym_profile_view_btn",
    )
    async def view_button(self, button: discord.ui.Button, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        cog = self.bot.get_cog("DatingProfileCog") or self.cog
        if not cog:
            return await interaction.followup.send("❌ Profile engine is currently offline.", ephemeral=True)

        profile = await cog.get_user_profile(interaction.user.id)
        if not profile:
            return await interaction.followup.send(
                "⚠️ You haven't created a profile yet. Click **Create Profile** to get started!",
                ephemeral=True,
            )
        embed = cog.build_profile_embed(interaction.user, profile)
        await interaction.followup.send(embed=embed, ephemeral=True)

    @discord.ui.button(
        label="Delete My Profile",
        style=discord.ButtonStyle.danger,
        custom_id="nym_profile_delete_btn",
    )
    async def delete_button(self, button: discord.ui.Button, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        cog = self.bot.get_cog("DatingProfileCog") or self.cog
        if not cog:
            return await interaction.followup.send("❌ Profile engine is currently offline.", ephemeral=True)

        profile = await cog.get_user_profile(interaction.user.id)
        if not profile:
            return await interaction.followup.send(
                "⚠️ You don't have an active profile to delete.", ephemeral=True
            )
        view = DeleteConfirmView(self.bot, cog, interaction.user.id)
        await interaction.followup.send(
            "⚠️ **Are you sure you want to permanently delete your Server Dating Profile?**",
            view=view,
            ephemeral=True,
        )



class ProfileBrowserView(discord.ui.View):
    """Interactive Browser View for discovering profiles in the server."""

    def __init__(self, bot: commands.Bot, cog: "DatingProfileCog", invoker: discord.Member, profiles: List[dict]):
        super().__init__(timeout=120)
        self.bot = bot
        self.cog = cog
        self.invoker = invoker
        self.profiles = profiles
        self.index = 0

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.invoker.id:
            await interaction.response.send_message("❌ Only the command invoker can navigate this browser.", ephemeral=True)
            return False
        return True

    async def update_page(self, interaction: discord.Interaction):
        target_data = self.profiles[self.index]
        target_member = interaction.guild.get_member(target_data["user_id"])
        if not target_member:
            try:
                target_member = await self.bot.fetch_user(target_data["user_id"])
            except Exception:
                target_member = interaction.user

        embed = self.cog.build_profile_embed(target_member, target_data)
        embed.set_footer(text=f"Profile {self.index + 1} of {len(self.profiles)} • Nym Discover")
        await interaction.response.edit_message(embed=embed, view=self)

    @discord.ui.button(label="Previous", style=discord.ButtonStyle.secondary, emoji="⬅️")
    async def prev_btn(self, button: discord.ui.Button, interaction: discord.Interaction):
        self.index = (self.index - 1) % len(self.profiles)
        await self.update_page(interaction)

    @discord.ui.button(label="Send Heart", style=discord.ButtonStyle.primary, emoji="💖")
    async def heart_btn(self, button: discord.ui.Button, interaction: discord.Interaction):
        target_data = self.profiles[self.index]
        target_id = target_data["user_id"]

        if target_id == interaction.user.id:
            return await interaction.response.send_message("💖 You cannot send a heart to yourself!", ephemeral=True)

        success, new_count, msg = await self.cog.send_heart(interaction.user.id, target_id, interaction.guild.id)
        if success:
            target_data["hearts_count"] = new_count
            await interaction.response.send_message(f"💕 You sent a heart to <@{target_id}>! Total Hearts: `{new_count}`", ephemeral=True)
        else:
            await interaction.response.send_message(f"⚠️ {msg}", ephemeral=True)

    @discord.ui.button(label="Next", style=discord.ButtonStyle.secondary, emoji="➡️")
    async def next_btn(self, button: discord.ui.Button, interaction: discord.Interaction):
        self.index = (self.index + 1) % len(self.profiles)
        await self.update_page(interaction)


class DatingProfileCog(commands.Cog):
    """Server Dating & Matchmaking Profile Engine for Project Nym."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.bot.add_view(DatingProfilePanelView(bot, self))

    @commands.Cog.listener()
    async def on_ready(self):
        """Ensure persistent view listeners are registered on ready."""
        self.bot.add_view(DatingProfilePanelView(self.bot, self))

    # --- Storage Helpers ---

    async def get_user_profile(self, user_id: int) -> Optional[dict]:
        """Fetch user profile data from Redis or SQLite."""
        key = f"profile:user:{user_id}"

        if hasattr(self.bot, "upstash") and self.bot.upstash.is_configured:
            try:
                raw_data = await self.bot.upstash.get(key)
                if raw_data:
                    parsed = json.loads(raw_data)
                    if isinstance(parsed, dict):
                        if parsed.get("disabled"):
                            return None
                        return parsed
            except Exception as e:
                logger.warning(f"Upstash read failed for profile {user_id}: {e}")

        try:
            row = await self.bot.db.fetch_one(
                "SELECT * FROM dating_profiles WHERE user_id = ?", (user_id,)
            )
            if row:
                data = {
                    "user_id": row["user_id"],
                    "guild_id": row["guild_id"],
                    "age_gender": row["age_gender"],
                    "relationship_status": row["relationship_status"],
                    "bio": row["bio"],
                    "interests": row["interests"],
                    "image_url": row["image_url"],
                    "hearts_count": row["hearts_count"] or 0,
                }
                if hasattr(self.bot, "upstash") and self.bot.upstash.is_configured:
                    await self.bot.upstash.set(key, json.dumps(data))
                return data
        except Exception as e:
            logger.error(f"SQLite read error for profile {user_id}: {e}")

        return None

    async def save_user_profile(
        self,
        interaction: discord.Interaction,
        user: Union[discord.User, discord.Member],
        guild: discord.Guild,
        age_gender: str,
        status_looking: str,
        interests: str,
        bio: str,
        image_url: Optional[str] = None,
    ):
        """Save or update a user's dating profile."""
        key = f"profile:user:{user.id}"
        existing = await self.get_user_profile(user.id) or {}
        hearts_count = existing.get("hearts_count", 0)

        data = {
            "user_id": user.id,
            "guild_id": guild.id,
            "age_gender": age_gender,
            "relationship_status": status_looking,
            "bio": bio,
            "interests": interests,
            "image_url": image_url,
            "hearts_count": hearts_count,
        }

        # 1. SQLite
        await self.bot.db.execute(
            """
            INSERT INTO dating_profiles (user_id, guild_id, age_gender, relationship_status, bio, interests, image_url, hearts_count)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(user_id) DO UPDATE SET
                guild_id = excluded.guild_id,
                age_gender = excluded.age_gender,
                relationship_status = excluded.relationship_status,
                bio = excluded.bio,
                interests = excluded.interests,
                image_url = excluded.image_url,
                updated_at = CURRENT_TIMESTAMP
            """,
            (user.id, guild.id, age_gender, status_looking, bio, interests, image_url, hearts_count),
        )

        # 2. Redis
        if hasattr(self.bot, "upstash") and self.bot.upstash.is_configured:
            try:
                await self.bot.upstash.set(key, json.dumps(data))
            except Exception as e:
                logger.warning(f"Upstash set failed for profile {user.id}: {e}")

        embed = self.build_profile_embed(user, data)
        msg = "✨ **Your Server Dating Profile has been updated successfully!**"
        if interaction.response.is_done():
            await interaction.followup.send(content=msg, embed=embed, ephemeral=True)
        else:
            await interaction.response.send_message(content=msg, embed=embed, ephemeral=True)

    async def delete_user_profile(self, interaction: discord.Interaction, user: Union[discord.User, discord.Member]):
        """Delete a user's profile data."""
        key = f"profile:user:{user.id}"

        # 1. SQLite
        await self.bot.db.execute("DELETE FROM dating_profiles WHERE user_id = ?", (user.id,))
        await self.bot.db.execute("DELETE FROM profile_likes WHERE target_id = ?", (user.id,))

        # 2. Redis
        if hasattr(self.bot, "upstash") and self.bot.upstash.is_configured:
            try:
                await self.bot.upstash.delete(key)
                await self.bot.upstash.set(key, json.dumps({"disabled": True}), ex_seconds=86400)
            except Exception as e:
                logger.warning(f"Upstash delete failed for profile {user.id}: {e}")

        if interaction.response.is_done():
            await interaction.followup.send("🗑️ **Your Server Dating Profile has been deleted.**", ephemeral=True)
        else:
            await interaction.response.edit_message(content="🗑️ **Your Server Dating Profile has been deleted.**", embed=None, view=None)

    async def send_heart(self, liker_id: int, target_id: int, guild_id: int) -> tuple[bool, int, str]:
        """Send a heart to a user profile, preventing duplicates."""
        row = await self.bot.db.fetch_one(
            "SELECT 1 FROM profile_likes WHERE liker_id = ? AND target_id = ?",
            (liker_id, target_id),
        )
        if row:
            return False, 0, "You have already sent a heart to this user!"

        await self.bot.db.execute(
            "INSERT INTO profile_likes (liker_id, target_id) VALUES (?, ?)",
            (liker_id, target_id),
        )

        profile = await self.get_user_profile(target_id)
        if not profile:
            return False, 0, "Target profile not found."

        new_count = profile.get("hearts_count", 0) + 1
        profile["hearts_count"] = new_count

        await self.bot.db.execute(
            "UPDATE dating_profiles SET hearts_count = ? WHERE user_id = ?",
            (new_count, target_id),
        )

        key = f"profile:user:{target_id}"
        if hasattr(self.bot, "upstash") and self.bot.upstash.is_configured:
            try:
                await self.bot.upstash.set(key, json.dumps(profile))
            except Exception:
                pass

        return True, new_count, "Success"

    def build_profile_embed(self, user: Union[discord.User, discord.Member], data: dict) -> discord.Embed:
        """Build an aesthetic Nekotina-styled profile card embed."""
        avatar_url = user.display_avatar.url if hasattr(user, "display_avatar") else user.default_avatar.url

        embed = EmbedBuilder.base(
            title=f"🌸 Server Profile — {user.display_name}",
            description=f"*✨ Welcome to {user.display_name}'s card.*",
            color=EmbedBuilder.COLOR_NEKOTINA,
            thumbnail_url=avatar_url,
        )

        embed.add_field(
            name="👤 Identity & Pronouns",
            value=f"`{data.get('age_gender', 'N/A')}`",
            inline=True,
        )
        embed.add_field(
            name="💕 Status & Looking For",
            value=f"`{data.get('relationship_status', 'N/A')}`",
            inline=True,
        )
        embed.add_field(
            name="💖 Hearts Received",
            value=f"**`💕 {data.get('hearts_count', 0)}`**",
            inline=True,
        )
        embed.add_field(
            name="🎮 Interests & Hobbies",
            value=f"> {data.get('interests', 'N/A')}",
            inline=False,
        )
        embed.add_field(
            name="📝 About Me",
            value=f">>> {data.get('bio', 'No bio provided.')}",
            inline=False,
        )

        img = data.get("image_url")
        if img and isinstance(img, str) and img.strip():
            clean_img = img.strip()
            if clean_img.startswith("http://") or clean_img.startswith("https://"):
                try:
                    embed.set_image(url=clean_img)
                except Exception:
                    pass

        return embed

    # --- Commands ---

    profile = discord.SlashCommandGroup("profile", "Server Dating Profile Engine and discovery controls.")

    @profile.command(name="panel", description="Post the interactive Dating Profile Portal panel to the channel.")
    async def profile_panel_slash(
        self,
        ctx: discord.ApplicationContext,
        channel: Optional[discord.TextChannel] = discord.Option(
            description="Target channel (Defaults to current channel)", default=None
        ),
    ):
        """Post main profile management panel with Create, Edit, View, and Delete buttons."""
        if not ctx.author.guild_permissions.manage_channels and not ctx.author.guild_permissions.administrator:
            return await ctx.respond("❌ You need **Manage Channels** or **Administrator** permission to post the profile panel.", ephemeral=True)

        target_ch = channel or ctx.channel

        embed = EmbedBuilder.base(
            title="👤 Your Dating Profile",
            description="*Create your Server Profile so others can get to know you. Explore profiles around the server and send a heart to people you like.* 💕\n\n"
                        "**Create and manage your profile below!**",
            color=EmbedBuilder.COLOR_NEKOTINA,
        )
        view = DatingProfilePanelView(self.bot, self)

        try:
            await target_ch.send(embed=embed, view=view)
            await ctx.respond(f"✅ Dating Profile Portal posted to {target_ch.mention}.", ephemeral=True)
        except Exception as e:
            await ctx.respond(f"❌ Failed posting panel: {e}", ephemeral=True)

    @profile.command(name="view", description="View a member's Server Dating Profile card.")
    async def profile_view_slash(
        self,
        ctx: discord.ApplicationContext,
        member: Optional[discord.Member] = discord.Option(description="Target member (Defaults to yourself)", default=None),
    ):
        """View a member's dating profile card."""
        target_member = member or ctx.author
        profile = await self.get_user_profile(target_member.id)

        if not profile:
            embed = EmbedBuilder.warning(
                "No Profile Found",
                f"{target_member.mention} hasn't created a Dating Profile yet.",
            )
            return await ctx.respond(embed=embed, ephemeral=True)

        embed = self.build_profile_embed(target_member, profile)
        await ctx.respond(embed=embed)

    @profile.command(name="discover", description="Browse and discover profiles around the server interactively.")
    async def profile_discover_slash(self, ctx: discord.ApplicationContext):
        """Browse server profiles interactively with Next/Previous and Send Heart buttons."""
        rows = await self.bot.db.fetch_all(
            "SELECT * FROM dating_profiles WHERE guild_id = ? ORDER BY hearts_count DESC LIMIT 50",
            (ctx.guild.id,),
        )
        if not rows:
            embed = EmbedBuilder.warning("No Profiles Available", "No members have created a Dating Profile in this server yet.")
            return await ctx.respond(embed=embed, ephemeral=True)

        profiles = [dict(r) for r in rows]
        view = ProfileBrowserView(self.bot, self, ctx.author, profiles)
        first_profile = profiles[0]
        first_member = ctx.guild.get_member(first_profile["user_id"]) or ctx.author

        embed = self.build_profile_embed(first_member, first_profile)
        embed.set_footer(text=f"Profile 1 of {len(profiles)} • Nym Discover")
        await ctx.respond(embed=embed, view=view)

    @profile.command(name="like", description="Send a heart to a member's dating profile.")
    async def profile_like_slash(self, ctx: discord.ApplicationContext, member: discord.Member):
        """Send a heart to a member's profile."""
        if member.id == ctx.author.id:
            return await ctx.respond("💖 You cannot send a heart to yourself!", ephemeral=True)

        success, new_count, msg = await self.send_heart(ctx.author.id, member.id, ctx.guild.id)
        if success:
            await ctx.respond(f"💕 You sent a heart to {member.mention}! Total Hearts: `{new_count}`")
        else:
            await ctx.respond(f"⚠️ {msg}", ephemeral=True)

    # --- Prefix Commands Fallback ---

    @commands.command(name="profile", aliases=["p", "card"])
    async def profile_prefix(self, ctx: commands.Context, member: Optional[discord.Member] = None):
        """Prefix command fallback (!profile [user] / !profile panel / !profile discover)."""
        target_member = member or ctx.author

        if ctx.message.content.lower().strip().endswith("panel") and (ctx.author.guild_permissions.manage_channels or ctx.author.guild_permissions.administrator):
            embed = EmbedBuilder.base(
                title="👤 Your Dating Profile",
                description="*Create your Server Profile so others can get to know you. Explore profiles around the server and send a heart to people you like.* 💕\n\n"
                            "**Create and manage your profile below!**",
                color=EmbedBuilder.COLOR_NEKOTINA,
            )
            view = DatingProfilePanelView(self.bot, self)
            return await ctx.channel.send(embed=embed, view=view)

        profile = await self.get_user_profile(target_member.id)
        if not profile:
            return await ctx.send(f"⚠️ {target_member.mention} hasn't created a Dating Profile yet.")

        embed = self.build_profile_embed(target_member, profile)
        await ctx.send(embed=embed)

    @commands.command(name="discover", aliases=["browse"])
    async def discover_prefix(self, ctx: commands.Context):
        """Prefix command fallback for browsing profiles (!discover)."""
        rows = await self.bot.db.fetch_all(
            "SELECT * FROM dating_profiles WHERE guild_id = ? ORDER BY hearts_count DESC LIMIT 50",
            (ctx.guild.id,),
        )
        if not rows:
            return await ctx.send("⚠️ No Dating Profiles found in this server yet.")

        profiles = [dict(r) for r in rows]
        view = ProfileBrowserView(self.bot, self, ctx.author, profiles)
        first_profile = profiles[0]
        first_member = ctx.guild.get_member(first_profile["user_id"]) or ctx.author

        embed = self.build_profile_embed(first_member, first_profile)
        embed.set_footer(text=f"Profile 1 of {len(profiles)} • Nym Discover")
        await ctx.send(embed=embed, view=view)


def setup(bot: commands.Bot):
    bot.add_cog(DatingProfileCog(bot))
