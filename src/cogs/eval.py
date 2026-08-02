import ast
import io
import os
import re
import sys
import time
import json
import math
import logging
import asyncio
import datetime
import traceback
from contextlib import redirect_stdout
from typing import Optional, Union, Any

import discord
from discord.ext import commands
from src.utils.embeds import EmbedBuilder
from src.utils.checks import is_trusted_admin


logger = logging.getLogger("Nym")



class EvalCog(commands.Cog):
    """Advanced Developer & Owner Evaluation Engine for Project Nym.

    Allows bot owners to execute arbitrary Python code directly within Nym's runtime environment
    with automatic expression returns, rich context shortcuts, stdout capture, and file execution.
    """

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    def _clean_code(self, code: str) -> str:
        """Clean markdown formatting and codeblocks from code input."""
        code = code.strip()
        if code.startswith("```"):
            lines = code.split("\n")
            if lines[0].startswith("```"):
                lines = lines[1:]
            if lines and lines[-1].startswith("```"):
                lines = lines[:-1]
            return "\n".join(lines).strip()
        return code

    def _wrap_code(self, code: str) -> ast.Module:
        """Parses and wraps code in an async function, transforming the last expression to a return statement."""
        parsed = ast.parse(code)

        # If the last node in the body is an expression, convert it to a return statement
        if parsed.body and isinstance(parsed.body[-1], ast.Expr):
            parsed.body[-1] = ast.Return(value=parsed.body[-1].value)

        ast.fix_missing_locations(parsed)

        # Wrap in async def __eval_func__()
        func_def = ast.AsyncFunctionDef(
            name="__eval_func__",
            args=ast.arguments(
                posonlyargs=[], args=[], vararg=None, kwonlyargs=[], kw_defaults=[], kwarg=None, defaults=[]
            ),
            body=parsed.body,
            decorator_list=[],
            returns=None,
        )

        module = ast.Module(body=[func_def], type_ignores=[])
        ast.fix_missing_locations(module)
        return module

    async def _execute_eval(self, ctx: Union[discord.ApplicationContext, commands.Context], code: str):
        """Core evaluation engine executing Python code in an async sandbox."""
        code = self._clean_code(code)

        if not code:
            embed = EmbedBuilder.warning("No Code Provided", "Please provide valid Python code to evaluate.")
            if isinstance(ctx, discord.ApplicationContext):
                return await ctx.respond(embed=embed, ephemeral=True)
            return await ctx.send(embed=embed)

        stdout = io.StringIO()
        start_time = time.perf_counter()

        # Build rich execution context environment
        guild = getattr(ctx, "guild", None)
        author = getattr(ctx, "author", None)
        channel = getattr(ctx, "channel", None)
        message = getattr(ctx, "message", None)
        bot_member = guild.me if guild else self.bot.user

        env: dict[str, Any] = {
            "bot": self.bot,
            "ctx": ctx,
            "guild": guild,
            "channel": channel,
            "author": author,
            "message": message,
            "msg": message,
            "me": bot_member,
            "db": self.bot.db,
            "upstash": getattr(self.bot, "upstash", None),
            "discord": discord,
            "asyncio": asyncio,
            "datetime": datetime.datetime,
            "timedelta": datetime.timedelta,
            "time": time,
            "os": os,
            "sys": sys,
            "json": json,
            "re": re,
            "math": math,
            "logging": logging,
        }

        try:
            # Transform AST for implicit last-line return
            try:
                wrapped_ast = self._wrap_code(code)
                compiled_code = compile(wrapped_ast, filename="<eval>", mode="exec")
                exec(compiled_code, env)
            except SyntaxError:
                # Fallback to standard execution if AST transformation fails
                body = "\n".join(f"    {line}" for line in code.split("\n"))
                exec(f"async def __eval_func__():\n{body}", env)

            func = env["__eval_func__"]

            # Execute function and capture stdout
            with redirect_stdout(stdout):
                result = await func()

            execution_time = round((time.perf_counter() - start_time) * 1000, 2)
            stdout_str = stdout.getvalue().strip()

            # Format outputs
            output_parts = []
            if stdout_str:
                output_parts.append(f"**Stdout Output:**\n```py\n{stdout_str}\n```")
            if result is not None:
                output_parts.append(f"**Return Value:**\n```py\n{repr(result)}\n```")
            if not output_parts:
                output_parts.append("```\n(Executed successfully with no output)\n```")

            response_text = "\n".join(output_parts)

            # Handle response length limits
            if len(response_text) > 1900:
                full_log = f"--- EVALUATION TELEMETRY ---\nExecution Time: {execution_time} ms\n\n--- STDOUT ---\n{stdout_str}\n\n--- RETURN ---\n{repr(result)}"
                file = discord.File(
                    io.BytesIO(full_log.encode("utf-8")),
                    filename=f"eval_output_{int(time.time())}.txt"
                )
                embed = EmbedBuilder.success(
                    title="⚡ Evaluation Completed",
                    description=f"Output exceeded character limit. Full telemetry attached.\n**Execution Time:** `{execution_time} ms`"
                )
                if isinstance(ctx, discord.ApplicationContext):
                    await ctx.respond(embed=embed, file=file, ephemeral=True)
                else:
                    await ctx.send(embed=embed, file=file)
            else:
                embed = EmbedBuilder.success(
                    title="⚡ Evaluation Completed",
                    description=f"{response_text}\n\n**Execution Time:** `{execution_time} ms`"
                )
                if isinstance(ctx, discord.ApplicationContext):
                    await ctx.respond(embed=embed, ephemeral=True)
                else:
                    await ctx.send(embed=embed)

        except Exception as e:
            execution_time = round((time.perf_counter() - start_time) * 1000, 2)
            err_traceback = traceback.format_exc()
            clean_err = f"{type(e).__name__}: {e}"

            embed = EmbedBuilder.error(
                title="❌ Evaluation Error",
                description=f"**Error:**\n```py\n{clean_err}\n```\n**Execution Time:** `{execution_time} ms`"
            )

            # Attach full traceback if detailed
            if len(err_traceback) > 1500:
                file = discord.File(
                    io.BytesIO(err_traceback.encode("utf-8")),
                    filename=f"eval_error_{int(time.time())}.log"
                )
                if isinstance(ctx, discord.ApplicationContext):
                    await ctx.respond(embed=embed, file=file, ephemeral=True)
                else:
                    await ctx.send(embed=embed, file=file)
            else:
                embed.description += f"\n**Traceback:**\n```py\n{err_traceback[:1000]}\n```"
                if isinstance(ctx, discord.ApplicationContext):
                    await ctx.respond(embed=embed, ephemeral=True)
                else:
                    await ctx.send(embed=embed)

    # --- Commands ---

    @discord.slash_command(name="eval", description="[Trusted Admin Only] Evaluate Python code in Nym runtime.")
    async def eval_slash(self, ctx: discord.ApplicationContext, code: str):
        """Slash command for trusted admin code evaluation."""
        if not await is_trusted_admin(ctx):
            embed = EmbedBuilder.error("Access Denied", "Only Bot Owners and trusted Bot Admins can use eval.")
            return await ctx.respond(embed=embed, ephemeral=True)
        await self._execute_eval(ctx, code)

    @commands.command(name="eval")
    async def eval_prefix(self, ctx: commands.Context, *, code: str):
        """Prefix command for trusted admin code evaluation (!eval <code>)."""
        if not await is_trusted_admin(ctx):
            embed = EmbedBuilder.error("Access Denied", "Only Bot Owners and trusted Bot Admins can use eval.")
            return await ctx.send(embed=embed)
        await self._execute_eval(ctx, code)

    @commands.command(name="evalfile")
    async def eval_file(self, ctx: commands.Context):
        """Prefix command to evaluate code from an attached .py or .txt file."""
        if not await is_trusted_admin(ctx):
            embed = EmbedBuilder.error("Access Denied", "Only Bot Owners and trusted Bot Admins can use eval.")
            return await ctx.send(embed=embed)
        if not ctx.message.attachments:
            return await ctx.send("❌ Please attach a `.py` or `.txt` file containing code to evaluate.")

        attachment = ctx.message.attachments[0]
        code_bytes = await attachment.read()
        code_text = code_bytes.decode("utf-8", errors="replace")
        await self._execute_eval(ctx, code_text)



def setup(bot: commands.Bot):
    bot.add_cog(EvalCog(bot))
