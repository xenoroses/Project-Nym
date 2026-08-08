import datetime
from typing import Optional, Union
import discord


class EmbedBuilder:
    """Clean, aesthetic, high-class Embed Builder for Project Nym."""

    # Muted aesthetic color palette
    COLOR_NEKOTINA = discord.Color.from_rgb(255, 115, 150) # Nekotina Muted Pink (#FF7396)
    COLOR_PRIMARY  = discord.Color.from_rgb(114, 137, 218) # Muted Blurple (#7289DA)
    COLOR_SUCCESS  = discord.Color.from_rgb(87, 242, 135)  # Soft Emerald (#57F287)
    COLOR_WARNING  = discord.Color.from_rgb(254, 231, 92)  # Muted Amber (#FEE75C)
    COLOR_ERROR    = discord.Color.from_rgb(237, 66, 69)   # Soft Ruby (#ED4245)

    @classmethod
    def base(
        cls,
        title: str,
        description: str,
        color: discord.Color = COLOR_NEKOTINA,
        author: Optional[Union[discord.User, discord.Member]] = None,
        footer: Optional[str] = None,
        thumbnail_url: Optional[str] = None,
        include_timestamp: bool = False,
    ) -> discord.Embed:
        """Create a clean, minimalist base embed."""
        ts = datetime.datetime.now(datetime.timezone.utc) if include_timestamp else None
        embed = discord.Embed(
            title=title,
            description=description,
            color=color,
            timestamp=ts,
        )

        if footer:
            embed.set_footer(text=footer)

        if thumbnail_url:
            embed.set_thumbnail(url=thumbnail_url)

        return embed

    @classmethod
    def info(
        cls,
        title: str,
        description: str,
        author: Optional[Union[discord.User, discord.Member]] = None,
        footer: Optional[str] = None,
    ) -> discord.Embed:
        return cls.base(
            title=title,
            description=description,
            color=cls.COLOR_PRIMARY,
            author=author,
            footer=footer,
        )

    @classmethod
    def success(
        cls,
        title: str,
        description: str,
        author: Optional[Union[discord.User, discord.Member]] = None,
        footer: Optional[str] = None,
    ) -> discord.Embed:
        return cls.base(
            title=title,
            description=description,
            color=cls.COLOR_SUCCESS,
            author=author,
            footer=footer,
        )

    @classmethod
    def warning(
        cls,
        title: str,
        description: str,
        author: Optional[Union[discord.User, discord.Member]] = None,
        footer: Optional[str] = None,
    ) -> discord.Embed:
        return cls.base(
            title=title,
            description=description,
            color=cls.COLOR_WARNING,
            author=author,
            footer=footer,
        )

    @classmethod
    def error(
        cls,
        title: str,
        description: str,
        author: Optional[Union[discord.User, discord.Member]] = None,
        footer: Optional[str] = None,
    ) -> discord.Embed:
        return cls.base(
            title=title,
            description=description,
            color=cls.COLOR_ERROR,
            author=author,
            footer=footer,
        )
