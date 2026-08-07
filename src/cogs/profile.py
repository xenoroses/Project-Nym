import asyncio
import json
import logging
from datetime import datetime, timezone
from typing import Optional, Union, List, Any

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
            target_member = interaction.guild.get_member(target_id) or interaction.user
            await self.cog.sync_public_profile_posts(interaction.guild, target_member, target_data)
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

    @commands.Cog.listener()
    async def on_interaction(self, interaction: discord.Interaction):
        """Global interaction listener for public profile card heart buttons."""
        if not interaction.custom_id or not interaction.custom_id.startswith("nym_heart_"):
            return

        try:
            target_id = int(interaction.custom_id.split("_")[2])
        except Exception:
            return

        if interaction.user.id == target_id:
            return await interaction.response.send_message("💖 You cannot send a heart to your own profile!", ephemeral=True)

        success, new_count, msg = await self.send_heart(interaction.user.id, target_id, interaction.guild.id)
        if not success:
            return await interaction.response.send_message(f"⚠️ {msg}", ephemeral=True)

        profile = await self.get_user_profile(target_id)
        if profile:
            profile["hearts_count"] = new_count
            target_member = interaction.guild.get_member(target_id)
            if not target_member:
                try:
                    target_member = await self.bot.fetch_user(target_id)
                except Exception:
                    target_member = None

            if target_member:
                embed = self.build_profile_embed(target_member, profile)
                view = discord.ui.View(timeout=None)
                view.add_item(
                    discord.ui.Button(
                        label="Send Heart",
                        style=discord.ButtonStyle.primary,
                        emoji="💖",
                        custom_id=f"nym_heart_{target_id}",
                    )
                )
                try:
                    await interaction.message.edit(embed=embed, view=view)
                except Exception:
                    pass

                await self.sync_public_profile_posts(interaction.guild, target_member, profile)

        await interaction.response.send_message(f"💕 You sent a heart to <@{target_id}>! Total Hearts: `{new_count}`", ephemeral=True)

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

    def is_vip_or_booster(self, member: Union[discord.Member, discord.User]) -> bool:
        """Check if a member holds a VIP or Booster role."""
        if not hasattr(member, "roles"):
            return False
        for role in member.roles:
            name = role.name.lower()
            if "vip" in name or "booster" in name or "boost" in name:
                return True
        return False

    # --- Storage Helpers ---

    async def _get_profile_config(self, guild_id: int) -> Optional[dict]:
        """Fetch auto-posting channels config for a guild."""
        key = f"profile:config:{guild_id}"

        if hasattr(self.bot, "upstash") and self.bot.upstash.is_configured:
            try:
                raw_data = await self.bot.upstash.get(key)
                if raw_data:
                    parsed = json.loads(raw_data)
                    if isinstance(parsed, dict):
                        return parsed
            except Exception as e:
                logger.warning(f"Upstash read failed for profile config {guild_id}: {e}")

        try:
            row = await self.bot.db.fetch_one(
                "SELECT user_channel_id, vip_channel_id FROM profile_configs WHERE guild_id = ?",
                (guild_id,),
            )
            if row:
                data = {
                    "user_channel_id": row["user_channel_id"],
                    "vip_channel_id": row["vip_channel_id"],
                }
                if hasattr(self.bot, "upstash") and self.bot.upstash.is_configured:
                    await self.bot.upstash.set(key, json.dumps(data))
                return data
        except Exception as e:
            logger.error(f"SQLite read error for profile config {guild_id}: {e}")

        return None

    async def _set_profile_config(
        self,
        guild_id: int,
        user_channel_id: Optional[int] = None,
        vip_channel_id: Optional[int] = None,
    ) -> dict:
        """Update auto-posting channels config for a guild."""
        key = f"profile:config:{guild_id}"
        current = await self._get_profile_config(guild_id) or {
            "user_channel_id": None,
            "vip_channel_id": None,
        }

        if user_channel_id is not None:
            current["user_channel_id"] = user_channel_id
        if vip_channel_id is not None:
            current["vip_channel_id"] = vip_channel_id

        await self.bot.db.execute(
            """
            INSERT INTO profile_configs (guild_id, user_channel_id, vip_channel_id)
            VALUES (?, ?, ?)
            ON CONFLICT(guild_id) DO UPDATE SET
                user_channel_id = excluded.user_channel_id,
                vip_channel_id = excluded.vip_channel_id
            """,
            (guild_id, current["user_channel_id"], current["vip_channel_id"]),
        )

        if hasattr(self.bot, "upstash") and self.bot.upstash.is_configured:
            try:
                await self.bot.upstash.set(key, json.dumps(current))
            except Exception as e:
                logger.warning(f"Upstash set failed for profile config {guild_id}: {e}")

        return current

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
                    "posted_msg_id": row["posted_msg_id"],
                    "vip_msg_id": row["vip_msg_id"],
                }
                if hasattr(self.bot, "upstash") and self.bot.upstash.is_configured:
                    await self.bot.upstash.set(key, json.dumps(data))
                return data
        except Exception as e:
            logger.error(f"SQLite read error for profile {user_id}: {e}")

        return None

    async def sync_public_profile_posts(self, guild: discord.Guild, member: Union[discord.Member, discord.User], data: dict):
        """Auto-post or update public profile cards in #user-profiles and #vip-profiles."""
        if not guild:
            return

        config = await self._get_profile_config(guild.id)
        if not config:
            return

        embed = self.build_profile_embed(member, data)
        target_id = member.id

        view = discord.ui.View(timeout=None)
        view.add_item(
            discord.ui.Button(
                label="Send Heart",
                style=discord.ButtonStyle.primary,
                emoji="💖",
                custom_id=f"nym_heart_{target_id}",
            )
        )

        # 1. Main User Profiles Channel
        user_ch_id = config.get("user_channel_id")
        if user_ch_id:
            user_ch = guild.get_channel(user_ch_id) or self.bot.get_channel(user_ch_id)
            if not user_ch:
                try:
                    user_ch = await self.bot.fetch_channel(user_ch_id)
                except Exception as e:
                    logger.error(f"Failed to fetch user_ch {user_ch_id}: {e}")
                    user_ch = None

            if user_ch:
                posted_id = data.get("posted_msg_id")
                msg_obj = None
                if posted_id:
                    try:
                        msg_obj = await user_ch.fetch_message(posted_id)
                        await msg_obj.edit(embed=embed, view=view)
                    except Exception:
                        msg_obj = None

                if not msg_obj:
                    try:
                        new_msg = await user_ch.send(embed=embed, view=view)
                        data["posted_msg_id"] = new_msg.id
                        await self.bot.db.execute(
                            "UPDATE dating_profiles SET posted_msg_id = ? WHERE user_id = ?",
                            (new_msg.id, target_id),
                        )
                    except Exception as e:
                        logger.error(f"Failed sending public profile in channel {user_ch.id}: {e}")

        # 2. VIP / Booster Profiles Channel
        vip_ch_id = config.get("vip_channel_id")
        if vip_ch_id and self.is_vip_or_booster(member):
            vip_ch = guild.get_channel(vip_ch_id) or self.bot.get_channel(vip_ch_id)
            if not vip_ch:
                try:
                    vip_ch = await self.bot.fetch_channel(vip_ch_id)
                except Exception as e:
                    logger.error(f"Failed to fetch vip_ch {vip_ch_id}: {e}")
                    vip_ch = None

            if vip_ch:
                vip_id = data.get("vip_msg_id")
                msg_obj = None
                if vip_id:
                    try:
                        msg_obj = await vip_ch.fetch_message(vip_id)
                        await msg_obj.edit(embed=embed, view=view)
                    except Exception:
                        msg_obj = None

                if not msg_obj:
                    try:
                        new_msg = await vip_ch.send(embed=embed, view=view)
                        data["vip_msg_id"] = new_msg.id
                        await self.bot.db.execute(
                            "UPDATE dating_profiles SET vip_msg_id = ? WHERE user_id = ?",
                            (new_msg.id, target_id),
                        )
                    except Exception as e:
                        logger.error(f"Failed sending VIP profile in channel {vip_ch.id}: {e}")

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
        posted_msg_id = existing.get("posted_msg_id")
        vip_msg_id = existing.get("vip_msg_id")

        data = {
            "user_id": user.id,
            "guild_id": guild.id,
            "age_gender": age_gender,
            "relationship_status": status_looking,
            "bio": bio,
            "interests": interests,
            "image_url": image_url,
            "hearts_count": hearts_count,
            "posted_msg_id": posted_msg_id,
            "vip_msg_id": vip_msg_id,
        }

        # 1. SQLite
        await self.bot.db.execute(
            """
            INSERT INTO dating_profiles (user_id, guild_id, age_gender, relationship_status, bio, interests, image_url, hearts_count, posted_msg_id, vip_msg_id)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(user_id) DO UPDATE SET
                guild_id = excluded.guild_id,
                age_gender = excluded.age_gender,
                relationship_status = excluded.relationship_status,
                bio = excluded.bio,
                interests = excluded.interests,
                image_url = excluded.image_url,
                updated_at = CURRENT_TIMESTAMP
            """,
            (user.id, guild.id, age_gender, status_looking, bio, interests, image_url, hearts_count, posted_msg_id, vip_msg_id),
        )

        # 2. Redis
        if hasattr(self.bot, "upstash") and self.bot.upstash.is_configured:
            try:
                await self.bot.upstash.set(key, json.dumps(data))
            except Exception as e:
                logger.warning(f"Upstash set failed for profile {user.id}: {e}")

        # 3. Auto-post or update in public channels
        member_obj = guild.get_member(user.id) if guild else None
        if not member_obj:
            try:
                member_obj = await self.bot.fetch_user(user.id)
            except Exception:
                member_obj = user

        if guild:
            await self.sync_public_profile_posts(guild, member_obj, data)

        embed = self.build_profile_embed(user, data)
        msg = "✨ **Your Server Dating Profile has been updated successfully!**"
        if interaction.response.is_done():
            await interaction.followup.send(content=msg, embed=embed, ephemeral=True)
        else:
            await interaction.response.send_message(content=msg, embed=embed, ephemeral=True)

    async def delete_user_profile(self, interaction: discord.Interaction, user: Union[discord.User, discord.Member]):
        """Delete a user's profile data and remove posted cards."""
        key = f"profile:user:{user.id}"
        profile = await self.get_user_profile(user.id)

        if profile:
            posted_id = profile.get("posted_msg_id")
            vip_id = profile.get("vip_msg_id")
            config = await self._get_profile_config(interaction.guild.id)

            if config:
                if posted_id and config.get("user_channel_id"):
                    ch = interaction.guild.get_channel(config["user_channel_id"]) or self.bot.get_channel(config["user_channel_id"])
                    if not ch:
                        try:
                            ch = await self.bot.fetch_channel(config["user_channel_id"])
                        except Exception:
                            ch = None
                    if ch:
                        try:
                            m = await ch.fetch_message(posted_id)
                            await m.delete()
                        except Exception:
                            pass

                if vip_id and config.get("vip_channel_id"):
                    ch = interaction.guild.get_channel(config["vip_channel_id"]) or self.bot.get_channel(config["vip_channel_id"])
                    if not ch:
                        try:
                            ch = await self.bot.fetch_channel(config["vip_channel_id"])
                        except Exception:
                            ch = None
                    if ch:
                        try:
                            m = await ch.fetch_message(vip_id)
                            await m.delete()
                        except Exception:
                            pass

        # SQLite & Redis deletion
        await self.bot.db.execute("DELETE FROM dating_profiles WHERE user_id = ?", (user.id,))
        await self.bot.db.execute("DELETE FROM profile_likes WHERE target_id = ?", (user.id,))

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
            title=f"👤 Server Profile — {user.display_name}",
            description=f"*✨ Welcome to {user.display_name}'s card.*",
            color=EmbedBuilder.COLOR_NEKOTINA,
            thumbnail_url=avatar_url,
            footer="Click button to send heart",
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
            name="🎮 Interests & Hobbies",
            value=f"> {data.get('interests', 'N/A')}",
            inline=False,
        )
        embed.add_field(
            name="📝 About Me",
            value=f">>> {data.get('bio', 'No bio provided.')}",
            inline=False,
        )
        embed.add_field(
            name="💖 Hearts Received",
            value=f"**`💕 {data.get('hearts_count', 0)}`**",
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

    @profile.command(
        name="setup",
        description="[Admin Only] Set designated channels for public profile card auto-posting.",
    )
    async def profile_setup_slash(
        self,
        ctx: discord.ApplicationContext,
        channel: discord.Option(description="Channel for all user profiles (e.g. #user-profiles)"), # type: ignore
        vip_channel: discord.Option(description="Channel for VIP/Booster profiles (Optional)", default=None), # type: ignore
    ):
        """Configure public profile auto-posting channels."""
        if not ctx.author.guild_permissions.manage_channels and not ctx.author.guild_permissions.administrator:
            return await ctx.respond("❌ You need **Manage Channels** or **Administrator** permission.", ephemeral=True)

        user_ch_id = self.resolve_channel_id(channel)
        if not user_ch_id:
            return await ctx.respond("❌ Invalid user profiles channel specified.", ephemeral=True)

        user_ch = ctx.guild.get_channel(user_ch_id) or self.bot.get_channel(user_ch_id)
        if not user_ch:
            try:
                user_ch = await self.bot.fetch_channel(user_ch_id)
            except Exception:
                user_ch = None

        if not user_ch:
            return await ctx.respond(f"❌ Channel with ID `{user_ch_id}` not found in this server.", ephemeral=True)

        vip_ch_id = self.resolve_channel_id(vip_channel)
        vip_ch = ctx.guild.get_channel(vip_ch_id) or self.bot.get_channel(vip_ch_id) if vip_ch_id else None
        if vip_ch_id and not vip_ch:
            try:
                vip_ch = await self.bot.fetch_channel(vip_ch_id)
            except Exception:
                vip_ch = None

        await self._set_profile_config(
            guild_id=ctx.guild.id,
            user_channel_id=user_ch.id,
            vip_channel_id=vip_ch.id if vip_ch else None,
        )

        # Retro-active sync for existing profiles in database
        rows = await self.bot.db.fetch_all("SELECT * FROM dating_profiles WHERE guild_id = ?", (ctx.guild.id,))
        synced_count = 0
        for row in rows:
            p_data = dict(row)
            mem = ctx.guild.get_member(p_data["user_id"])
            if not mem:
                try:
                    mem = await self.bot.fetch_user(p_data["user_id"])
                except Exception:
                    mem = None
            if mem:
                await self.sync_public_profile_posts(ctx.guild, mem, p_data)
                synced_count += 1

        embed = EmbedBuilder.success(
            title="Profile Auto-Posting Configured",
            description=f"✧ **User Profiles Channel:** {user_ch.mention}\n"
                        f"• **VIP / Booster Channel:** {vip_ch.mention if vip_ch else '`Not Configured`'}\n"
                        f"• **Profiles Synced Now:** `{synced_count}` profile(s)\n\n"
                        f"✨ User profiles will now automatically post and update in these channels with interactive heart buttons!",
            author=ctx.author,
        )
        await ctx.respond(embed=embed, ephemeral=True)

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
            footer="",
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
            profile = await self.get_user_profile(member.id)
            if profile:
                await self.sync_public_profile_posts(ctx.guild, member, profile)
        else:
            await ctx.respond(f"⚠️ {msg}", ephemeral=True)

    # --- Prefix Commands Fallback ---

    @commands.command(name="profile", aliases=["p", "card"])
    async def profile_prefix(self, ctx: commands.Context, member: Optional[discord.Member] = None):
        """Prefix command fallback (!profile [user] / !profile panel / !profile setup #channel [#vip])."""
        clean_text = ctx.message.content.lower().strip()

        if "setup" in clean_text and (ctx.author.guild_permissions.manage_channels or ctx.author.guild_permissions.administrator):
            if len(ctx.message.channel_mentions) > 0:
                user_ch = ctx.message.channel_mentions[0]
                vip_ch = ctx.message.channel_mentions[1] if len(ctx.message.channel_mentions) > 1 else None
                await self._set_profile_config(ctx.guild.id, user_channel_id=user_ch.id, vip_channel_id=vip_ch.id if vip_ch else None)
                
                rows = await self.bot.db.fetch_all("SELECT * FROM dating_profiles WHERE guild_id = ?", (ctx.guild.id,))
                synced_count = 0
                for row in rows:
                    p_data = dict(row)
                    mem = ctx.guild.get_member(p_data["user_id"])
                    if not mem:
                        try:
                            mem = await self.bot.fetch_user(p_data["user_id"])
                        except Exception:
                            mem = None
                    if mem:
                        await self.sync_public_profile_posts(ctx.guild, mem, p_data)
                        synced_count += 1

                return await ctx.send(f"✧ Public profiles channel set to {user_ch.mention} (`{synced_count}` profiles synced).")
            return await ctx.send("⚠️ Usage: `!profile setup #user-profiles [#vip-profiles]`.")

        if clean_text.endswith("panel") and (ctx.author.guild_permissions.manage_channels or ctx.author.guild_permissions.administrator):
            embed = EmbedBuilder.base(
                title="👤 Your Dating Profile",
                description="*Create your Server Profile so others can get to know you. Explore profiles around the server and send a heart to people you like.* 💕\n\n"
                            "**Create and manage your profile below!**",
                color=EmbedBuilder.COLOR_NEKOTINA,
                footer="",
            )
            view = DatingProfilePanelView(self.bot, self)
            return await ctx.channel.send(embed=embed, view=view)

        target_member = member or ctx.author
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
