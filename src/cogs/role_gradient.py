import io
import re
import logging
from typing import Optional, Union, Tuple
from PIL import Image, ImageDraw

import discord
from discord.ext import commands
from src.utils.embeds import EmbedBuilder

logger = logging.getLogger("Nym")


def parse_hex_color(hex_str: str) -> Optional[Tuple[int, int, int]]:
    """Parse hex color string into (R, G, B) tuple."""
    clean = hex_str.strip().lstrip("#")
    if len(clean) == 3:
        clean = "".join([c * 2 for c in clean])
    if len(clean) != 6 or not re.fullmatch(r"[0-9a-fA-F]{6}", clean):
        return None
    try:
        return (
            int(clean[0:2], 16),
            int(clean[2:4], 16),
            int(clean[4:6], 16),
        )
    except ValueError:
        return None


def calculate_midpoint_color(rgb1: Tuple[int, int, int], rgb2: Tuple[int, int, int]) -> discord.Color:
    """Calculate linear 50/50 RGB blend between two colors."""
    r_mid = (rgb1[0] + rgb2[0]) // 2
    g_mid = (rgb1[1] + rgb2[1]) // 2
    b_mid = (rgb1[2] + rgb2[2]) // 2
    return discord.Color.from_rgb(r_mid, g_mid, b_mid)


def create_gradient_icon(rgb1: Tuple[int, int, int], rgb2: Tuple[int, int, int], size=(128, 128), style="circle") -> bytes:
    """Generate high-resolution PNG gradient icon image for Discord role display_icon."""
    w, h = size
    gradient = Image.new("RGBA", size)
    draw = ImageDraw.Draw(gradient)

    for x in range(w):
        factor = x / max(1, w - 1)
        r = int(rgb1[0] + (rgb2[0] - rgb1[0]) * factor)
        g = int(rgb1[1] + (rgb2[1] - rgb1[1]) * factor)
        b = int(rgb1[2] + (rgb2[2] - rgb1[2]) * factor)
        draw.line([(x, 0), (x, h)], fill=(r, g, b, 255))

    if style.lower() == "circle":
        mask = Image.new("L", size, 0)
        mask_draw = ImageDraw.Draw(mask)
        mask_draw.ellipse([4, 4, w - 4, h - 4], fill=255)

        output = Image.new("RGBA", size, (0, 0, 0, 0))
        output.paste(gradient, (0, 0), mask=mask)
        img = output
    else:
        img = gradient

    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


class GradientRoleCog(commands.Cog):
    """Dual-Hex Gradient Role Color & Custom Icon Generator for Project Nym."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    async def _process_gradient_role(
        self,
        ctx: Union[commands.Context, discord.ApplicationContext],
        role: discord.Role,
        hex1: str,
        hex2: str,
        style: str = "circle",
    ):
        guild = ctx.guild
        author = ctx.author if isinstance(ctx, commands.Context) else ctx.author

        # Permission verification
        if not author.guild_permissions.manage_roles and not author.guild_permissions.administrator:
            msg = "❌ You need **Manage Roles** or **Administrator** permission to set gradient role colors."
            if isinstance(ctx, commands.Context): return await ctx.send(msg)
            return await ctx.respond(msg, ephemeral=True)

        bot_member = guild.me
        if not bot_member.guild_permissions.manage_roles:
            msg = "❌ I do not have **Manage Roles** permission in this server."
            if isinstance(ctx, commands.Context): return await ctx.send(msg)
            return await ctx.respond(msg, ephemeral=True)

        if role >= bot_member.top_role:
            msg = f"❌ Cannot modify {role.mention} because it is equal to or higher than my top role in server hierarchy."
            if isinstance(ctx, commands.Context): return await ctx.send(msg)
            return await ctx.respond(msg, ephemeral=True)

        # Parse Hex colors
        rgb1 = parse_hex_color(hex1)
        rgb2 = parse_hex_color(hex2)

        if not rgb1:
            msg = f"❌ Invalid start hex color: `{hex1}`. Please use 6-character hex format (e.g. `#ffbf00` or `ffbf00`)."
            if isinstance(ctx, commands.Context): return await ctx.send(msg)
            return await ctx.respond(msg, ephemeral=True)

        if not rgb2:
            msg = f"❌ Invalid end hex color: `{hex2}`. Please use 6-character hex format (e.g. `#ffffff` or `ffffff`)."
            if isinstance(ctx, commands.Context): return await ctx.send(msg)
            return await ctx.respond(msg, ephemeral=True)

        # Calculate Midpoint & Render Gradient PNG Icon
        mid_color = calculate_midpoint_color(rgb1, rgb2)
        png_bytes = create_gradient_icon(rgb1, rgb2, style=style)
        hex1_clean = f"#{hex1.strip().lstrip('#').upper()}"
        hex2_clean = f"#{hex2.strip().lstrip('#').upper()}"
        mid_clean = f"#{str(mid_color).upper()}"

        icon_updated = False
        try:
            # Apply color and level 2/3 boost display_icon if supported
            await role.edit(
                color=mid_color,
                display_icon=png_bytes,
                reason=f"Gradient Role configured by {author} ({hex1_clean} -> {hex2_clean})",
            )
            icon_updated = True
        except discord.HTTPException:
            # Fallback if server lacks Level 2 boost feature for display_icon
            try:
                await role.edit(
                    color=mid_color,
                    reason=f"Gradient Role color configured by {author} ({hex1_clean} -> {hex2_clean})",
                )
            except Exception as e:
                msg = f"❌ Failed updating role: {e}"
                if isinstance(ctx, commands.Context): return await ctx.send(msg)
                return await ctx.respond(msg, ephemeral=True)

        # Build Rich Embed Confirmation with image preview
        file = discord.File(io.BytesIO(png_bytes), filename="gradient_icon.png")
        embed = discord.Embed(
            title="✨ Gradient Role Configured",
            description=f"Successfully applied dual-hex gradient color scheme to {role.mention}!",
            color=mid_color,
        )
        embed.set_thumbnail(url="attachment://gradient_icon.png")
        embed.add_field(name="🎨 Start Hex", value=f"`{hex1_clean}`", inline=True)
        embed.add_field(name="🎨 End Hex", value=f"`{hex2_clean}`", inline=True)
        embed.add_field(name="🔮 Blended Midpoint", value=f"`{mid_clean}`", inline=True)

        status_text = "✨ Custom 2-Color Gradient Icon & Midpoint Role Color applied!" if icon_updated else "✨ Midpoint Role Color applied!"
        embed.set_footer(text=f"{status_text} | Configured by {author.name}")

        if isinstance(ctx, commands.Context):
            await ctx.send(embed=embed, file=file)
        else:
            await ctx.respond(embed=embed, file=file)

    # --- Slash Commands ---

    @discord.slash_command(
        name="gradientrole",
        description="Set dual-hex gradient role colors & custom 2-color icon badge for a role.",
    )
    async def gradient_role_slash(
        self,
        ctx: discord.ApplicationContext,
        role: discord.Role = discord.Option(description="Target role to style"), # type: ignore
        hex1: str = discord.Option(description="Start hex color (e.g. #ffbf00)"), # type: ignore
        hex2: str = discord.Option(description="End hex color (e.g. #ffffff)"), # type: ignore
        style: str = discord.Option(
            description="Gradient icon shape style",
            choices=["circle", "linear"],
            default="circle",
        ),
    ):
        """Slash command for gradient roles."""
        await self._process_gradient_role(ctx, role, hex1, hex2, style)

    # --- Prefix Commands Fallback ---

    @commands.command(name="gradientrole", aliases=["rolegradient", "gradrole"])
    async def gradient_role_prefix(
        self,
        ctx: commands.Context,
        role: discord.Role,
        hex1: str,
        hex2: str,
        style: str = "circle",
    ):
        """Prefix command fallback (!gradientrole @Role #ffbf00 #ffffff / nym gradientrole <role_id> #ffbf00 #ffffff)."""
        await self._process_gradient_role(ctx, role, hex1, hex2, style)


def setup(bot: commands.Bot):
    bot.add_cog(GradientRoleCog(bot))
