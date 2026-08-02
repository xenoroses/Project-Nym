import io
import sys
import time
import trace
import asyncio
import inspect
import logging
from contextlib import redirect_stdout
from typing import Optional, Union
import discord
from discord.ext import commands

from src.utils.embeds import EmbedBuilder

logger = logging.getLogger("Nym")


class EvalCog(commands.Cog):
    """Developer & Owner Evaluation Engine.

    Allows bot owners to execute arbitrary Python code directly within Nym's runtime environment.
    """

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    def _clean_code(self, code: str) -> str:
        """Strip markdown codeblocks from input code."""
        code = code.strip()
        if code.startswith("```"):
            lines = code.split("\n")
            if lines[0].startswith("```"):
                lines = lines[1:]
            if lines and lines[-1].startswith("```"):
                lines = lines[:-1]
            return "\n".join(lines).strip()
        return code

    async def _execute_eval(self, ctx: Union[discord.ApplicationContext, commands.Context], code: str):
        """Core asynchronous evaluation execution handler."""
        code = self._clean_code(code)

        stdout = io.StringIO()
        start_time = time.perf_counter()

        env = {
            "bot": self.bot,
            "ctx": ctx,
            "channel": ctx.channel,
            "author": ctx.author,
            "guild": ctx.guild,
            "db": self.bot.db,
            "upstash": getattr(self.bot, "upstash", None),
            "discord": discord,
            "asyncio": asyncio,
            "sys": sys,
            "logging": logging,
        }

        # Wrap code inside an async function definition
        body = "\n".join(f"    {line}" for line in code.split("\n"))
        func_def = f"async def __eval_func__():\n{body}"

        try:
            exec(func_def, env)
            func = env["__eval_func__"]

            with redirect_stdout(stdout):
                result = await func()

            execution_time = round((time.perf_counter() - start_time) * 1000, 2)
            stdout_value = stdout.getvalue()

            # Format response text
            output_parts = []
            if stdout_value:
                output_parts.append(f"**Stdout:**\n```py\n{stdout_value.strip()}\n```")
            if result is not None:
                output_parts.append(f"**Return:**\n```py\n{repr(result)}\n```")
            if not output_parts:
                output_parts.append("```\n(Executed successfully with no output)\n```")

            response_text = "\n".join(output_parts)

            # If response is too long, send as file attachment
            if len(response_text) > 1900:
                file_data = f"--- STDOUT ---\n{stdout_value}\n\n--- RETURN ---\n{repr(result)}"
                file = discord.File(
                    io.BytesIO(file_data.encode("utf-8")),
                    filename=f"eval_result_{int(time.time())}.txt"
                )
                embed = EmbedBuilder.success(
                    title="⚡ Evaluation Completed",
                    description=f"Output exceeded 2000 characters. Detailed log attached.\n**Execution Time:** `{execution_time} ms`"
                )
                if isinstance(ctx, discord.ApplicationContext):
                    await ctx.respond(embed=embed, file=file, ephemeral=True)
                else:
                    await ctx.send(embed=embed, file=file)
            else:
                embed = EmbedBuilder.success(
                    title="⚡ Evaluation Successful",
                    description=f"{response_text}\n**Execution Time:** `{execution_time} ms`"
                )
                if isinstance(ctx, discord.ApplicationContext):
                    await ctx.respond(embed=embed, ephemeral=True)
                else:
                    await ctx.send(embed=embed)

        except Exception as e:
            execution_time = round((time.perf_counter() - start_time) * 1000, 2)
            error_text = f"**Error ({type(e).__name__}):**\n```py\n{e}\n```"
            embed = EmbedBuilder.error(
                title="❌ Evaluation Failed",
                description=f"{error_text}\n**Execution Time:** `{execution_time} ms`"
            )
            if isinstance(ctx, discord.ApplicationContext):
                await ctx.respond(embed=embed, ephemeral=True)
            else:
                await ctx.send(embed=embed)

    @discord.slash_command(name="eval", description="[Owner Only] Evaluate Python code dynamically.")
    @commands.is_owner()
    async def eval_slash(self, ctx: discord.ApplicationContext, code: str):
        """Slash command for owner Python code evaluation."""
        await self._execute_eval(ctx, code)

    @commands.command(name="eval")
    @commands.is_owner()
    async def eval_prefix(self, ctx: commands.Context, *, code: str):
        """Prefix command for owner Python code evaluation (!eval <code>)."""
        await self._execute_eval(ctx, code)


def setup(bot: commands.Bot):
    bot.add_cog(EvalCog(bot))
