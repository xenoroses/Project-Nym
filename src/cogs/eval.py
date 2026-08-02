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
import textwrap
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

    def _sanitize_traceback(self, text: str) -> str:
        """Sanitize local file paths and environment directories from tracebacks and errors to prevent info leaks."""
        text = re.sub(r'[A-Za-z]:\\[^\n"]*\\src\\', 'src/', text)
        text = re.sub(r'[A-Za-z]:\\[^\n"]*\\.venv\\[^\n"]*', '[virtualenv]', text)
        text = re.sub(r'[A-Za-z]:\\[^\n"]*\\Python\d*\\[^\n"]*', '[python_lib]', text)
        text = re.sub(r'[A-Za-z]:\\[^\n"]*', '[system_core]', text)
        text = re.sub(r'/Users/[^\n"]*/src/', 'src/', text)
        text = re.sub(r'/home/[^\n"]*/src/', 'src/', text)
        return text

    def _clean_code(self, code: str) -> str:
        """Clean markdown formatting, codeblocks, and uneven leading indentation."""
        code = code.strip()
        if code.startswith("```"):
            lines = code.split("\n")
            if lines[0].startswith("```"):
                lines = lines[1:]
            if lines and lines[-1].startswith("```"):
                lines = lines[:-1]
            code = "\n".join(lines)

        dedented = textwrap.dedent(code).strip()
        lines = dedented.split("\n")
        if lines:
            lines[0] = lines[0].lstrip()
            dedented = textwrap.dedent("\n".join(lines)).strip()

        return dedented

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

    async def _reply(
        self,
        ctx: Union[discord.ApplicationContext, commands.Context],
        embed: discord.Embed,
        file: Optional[discord.File] = None,
    ) -> None:
        """Safely send evaluation output to context, fallback to DM if channel is deleted/not found."""
        try:
            if isinstance(ctx, discord.ApplicationContext):
                if file:
                    await ctx.respond(embed=embed, file=file, ephemeral=True)
                else:
                    await ctx.respond(embed=embed, ephemeral=True)
            else:
                if file:
                    await ctx.send(embed=embed, file=file)
                else:
                    await ctx.send(embed=embed)
        except discord.NotFound:
            # Channel was deleted or context is unknown, fallback to DMing author
            try:
                if file:
                    await ctx.author.send(embed=embed, file=file)
                else:
                    await ctx.author.send(embed=embed)
            except Exception as e:
                logger.warning(f"Could not send eval output to channel or DM: {e}")
        except Exception as e:
            logger.warning(f"Failed to send eval response: {e}")

    def _format_single_item(self, item: Any) -> str:
        """Helper to format individual Discord or Python objects cleanly."""
        if isinstance(item, discord.Message):
            return f"`Message` (`ID: {item.id}`)"
        if isinstance(item, discord.abc.GuildChannel):
            return f"📁 `{item.name}` (`ID: {item.id}`)"
        if isinstance(item, (discord.Member, discord.User)):
            return f"👤 `{item.name}` (`ID: {item.id}`)"
        if isinstance(item, discord.Role):
            return f"🏷️ `{item.name}` (`ID: {item.id}`)"
        if isinstance(item, discord.Embed):
            return f"🖼️ `Embed` (**{item.title or 'No Title'}**)"
        return repr(item)

    def _format_eval_result(self, result: Any) -> Optional[str]:
        """Format return values cleanly with Nekotina aesthetics."""
        if result is None:
            return None

        # Clean formatting for single Discord Objects
        if isinstance(result, discord.Message):
            return f"📤 `Message Sent` (ID: `{result.id}` | Channel: {result.channel.mention})"
        if isinstance(result, discord.abc.GuildChannel):
            return f"📁 Channel **{result.name}** (ID: `{result.id}`)"
        if isinstance(result, discord.Embed):
            return f"🖼️ `discord.Embed` (Title: **{result.title or 'No Title'}**)"
        if isinstance(result, (discord.Member, discord.User)):
            return f"👤 `{result.name}` (ID: `{result.id}`)"
        if isinstance(result, discord.Guild):
            return f"🏰 `{result.name}` (ID: `{result.id}`)"

        # Clean formatting for Lists, Sets, and Tuples
        if isinstance(result, (list, set, tuple)):
            items = list(result)
            total = len(items)
            if total == 0:
                return "```py\n[] (Empty List)\n```"

            formatted_items = [self._format_single_item(x) for x in items[:6]]
            summary = "\n".join(f"• {item}" for item in formatted_items)
            if total > 6:
                summary += f"\n*... and {total - 6} more items (Total: {total}).*"
            return f"📋 **Batch Operation Result ({total} items):**\n{summary}"

        # Clean formatting for Dicts
        if isinstance(result, dict):
            try:
                formatted = json.dumps(result, indent=2, default=str)
                if len(formatted) < 800:
                    return f"```json\n{formatted}\n```"
            except Exception:
                pass

        repr_str = repr(result)
        if len(repr_str) > 800:
            repr_str = repr_str[:797] + "..."

        return f"```py\n{repr_str}\n```"

    async def _execute_eval(self, ctx: Union[discord.ApplicationContext, commands.Context], code: str):
        """Core evaluation engine executing Python code in an async sandbox with Nekotina aesthetics."""
        code = self._clean_code(code)

        if not code:
            embed = EmbedBuilder.warning("No Code Provided", "Please provide valid Python code to evaluate.")
            return await self._reply(ctx, embed)

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
            except (SyntaxError, IndentationError):
                # Fallback to standard execution if AST transformation fails
                indented_body = textwrap.indent(code, "    ")
                exec(f"async def __eval_func__():\n{indented_body}", env)

            func = env["__eval_func__"]

            # Execute function and capture stdout
            with redirect_stdout(stdout):
                result = await func()

            execution_time = round((time.perf_counter() - start_time) * 1000, 2)
            stdout_str = stdout.getvalue().strip()
            formatted_result = self._format_eval_result(result)

            # Build Nekotina-styled result embed
            embed = EmbedBuilder.base(
                title="⚡ Evaluation Result",
                description="*Code executed in Nym async runtime.*",
                color=EmbedBuilder.COLOR_NEKOTINA,
                author=author,
                footer=f"Execution Latency: {execution_time} ms"
            )

            if stdout_str:
                embed.add_field(name="📤 Stdout Output", value=f"```py\n{stdout_str[:1000]}\n```", inline=False)

            if formatted_result:
                embed.add_field(name="📥 Return Value", value=formatted_result, inline=False)

            if not stdout_str and not formatted_result:
                embed.add_field(name="✨ Status", value="`Executed cleanly with no return value.`", inline=False)

            embed.add_field(name="⏱️ Execution Latency", value=f"`{execution_time} ms`", inline=True)

            # Attachment fallback ONLY if stdout itself is huge
            if len(stdout_str) > 1800:
                full_log = f"--- EVALUATION TELEMETRY ---\nExecution Time: {execution_time} ms\n\n--- STDOUT ---\n{stdout_str}\n\n--- RETURN ---\n{repr(result)}"
                file = discord.File(
                    io.BytesIO(full_log.encode("utf-8")),
                    filename=f"eval_stdout_{int(time.time())}.txt"
                )
                await self._reply(ctx, embed, file=file)
            else:
                await self._reply(ctx, embed)


        except Exception as e:
            execution_time = round((time.perf_counter() - start_time) * 1000, 2)
            raw_err_traceback = traceback.format_exc()
            err_traceback = self._sanitize_traceback(raw_err_traceback)
            clean_err = self._sanitize_traceback(f"{type(e).__name__}: {e}")

            embed = EmbedBuilder.base(
                title="❌ Evaluation Error",
                description=f"```py\n{clean_err}\n```",
                color=EmbedBuilder.COLOR_ERROR,
                author=author,
                footer=f"Execution Latency: {execution_time} ms"
            )

            if len(err_traceback) > 1000:
                clean_tb = err_traceback[:900] + "\n... [truncated]"
                embed.add_field(name="📋 Stack Trace", value=f"```py\n{clean_tb}\n```", inline=False)
            else:
                embed.add_field(name="📋 Stack Trace", value=f"```py\n{err_traceback}\n```", inline=False)

            embed.add_field(name="⏱️ Execution Latency", value=f"`{execution_time} ms`", inline=True)

            # Full file attachment if error is huge
            if len(err_traceback) > 1500:
                file = discord.File(
                    io.BytesIO(err_traceback.encode("utf-8")),
                    filename=f"eval_error_{int(time.time())}.log"
                )
                await self._reply(ctx, embed, file=file)
            else:
                await self._reply(ctx, embed)



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
