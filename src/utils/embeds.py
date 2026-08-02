from typing import Optional
import discord


class EmbedBuilder:
    """Helper class for creating consistent Discord embeds across Nym."""

    COLOR_PRIMARY = discord.Color.from_rgb(114, 137, 218)  # Blurple
    COLOR_SUCCESS = discord.Color.from_rgb(87, 242, 135)   # Green
    COLOR_WARNING = discord.Color.from_rgb(254, 231, 92)   # Yellow
    COLOR_ERROR = discord.Color.from_rgb(237, 66, 69)      # Red

    @classmethod
    def info(cls, title: str, description: str, footer: Optional[str] = None) -> discord.Embed:
        embed = discord.Embed(title=title, description=description, color=cls.COLOR_PRIMARY)
        if footer:
            embed.set_footer(text=footer)
        return embed

    @classmethod
    def success(cls, title: str, description: str, footer: Optional[str] = None) -> discord.Embed:
        embed = discord.Embed(title=f"✅ {title}", description=description, color=cls.COLOR_SUCCESS)
        if footer:
            embed.set_footer(text=footer)
        return embed

    @classmethod
    def warning(cls, title: str, description: str, footer: Optional[str] = None) -> discord.Embed:
        embed = discord.Embed(title=f"⚠️ {title}", description=description, color=cls.COLOR_WARNING)
        if footer:
            embed.set_footer(text=footer)
        return embed

    @classmethod
    def error(cls, title: str, description: str, footer: Optional[str] = None) -> discord.Embed:
        embed = discord.Embed(title=f"❌ {title}", description=description, color=cls.COLOR_ERROR)
        if footer:
            embed.set_footer(text=footer)
        return embed
