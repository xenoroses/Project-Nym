import discord


class ConfirmView(discord.ui.View):
    """Example Discord UI View with interactive buttons."""

    def __init__(self, author_id: int, timeout: float = 60.0):
        super().__init__(timeout=timeout)
        self.author_id = author_id
        self.value: bool | None = None

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        """Ensure only the command invoker can click the buttons."""
        if interaction.user.id != self.author_id:
            await interaction.response.send_message(
                "❌ You are not allowed to interact with this menu.", ephemeral=True
            )
            return False
        return True

    @discord.ui.button(label="Confirm", style=discord.ButtonStyle.green, emoji="✅")
    async def confirm_callback(self, button: discord.ui.Button, interaction: discord.Interaction):
        self.value = True
        self.disable_all_items()
        await interaction.response.edit_message(
            content="Action confirmed! ✅", view=self
        )
        self.stop()

    @discord.ui.button(label="Cancel", style=discord.ButtonStyle.red, emoji="❌")
    async def cancel_callback(self, button: discord.ui.Button, interaction: discord.Interaction):
        self.value = False
        self.disable_all_items()
        await interaction.response.edit_message(
            content="Action cancelled. ❌", view=self
        )
        self.stop()
