import datetime
from typing import Optional, Union
import discord


class EmbedBuilder:
    """Nekotina-inspired aesthetic Embed Builder for Project Nym."""

    # Nekotina signature palette
    COLOR_NEKOTINA = discord.Color.from_rgb(255, 115, 150) # Nekotina Soft Pink (#FF7396)
    COLOR_PRIMARY  = discord.Color.from_rgb(114, 137, 218) # Blurple (#7289DA)
    COLOR_SUCCESS  = discord.Color.from_rgb(87, 242, 135)  # Soft Emerald (#57F287)
    COLOR_WARNING  = discord.Color.from_rgb(254, 231, 92)  # Amber (#FEE75C)
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
        """Create a styled base embed matching Nekotina visual guidelines."""
        ts = datetime.datetime.now(datetime.timezone.utc) if include_timestamp else None
        embed = discord.Embed(
            title=title,
            description=description,
            color=color,
            timestamp=ts,
        )

        if author:
            avatar_url = author.display_avatar.url if hasattr(author, "display_avatar") else None
            embed.set_author(name=f"Requested by {author.display_name}", icon_url=avatar_url)

        if footer is not None:
            if footer:
                embed.set_footer(text=footer)
        else:
            embed.set_footer(text="Type /help or nym help")


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
            title=f"✧ {title}",
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
            title=f"✅ {title}",
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
            title=f"⚠️ {title}",
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
            title=f"❌ {title}",
            description=description,
            color=cls.COLOR_ERROR,
            author=author,
            footer=footer,
        )
