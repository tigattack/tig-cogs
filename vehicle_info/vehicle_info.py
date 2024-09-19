import logging
from typing import Optional

from celtic_tuning import PowerUnits, TorqueUnits
from discord import ButtonStyle, Colour, Embed, Interaction, InteractionMessage
from discord.ui import Button, View
from redbot.core import Config, app_commands, commands
from redbot.core.bot import Red

from . import config_utils
from .models import VehicleData
from .vehicle_utils import fetch_vehicle_data, gen_main_embed, gen_mot_embed

log = logging.getLogger("red.tigattack.vehicle_info")


class Buttons(View):
    def __init__(self, interaction: InteractionMessage, vehicle_data: VehicleData, *, timeout: float = 180):
        super().__init__(timeout=timeout)
        self.vehicle_data = vehicle_data

        self.current_embed: Optional[Embed] = None
        self.interaction = interaction

        # Initial button setup: Start with "Main Info" disabled
        self.main_page_button: Button = Button(label="Back", style=ButtonStyle.primary)
        self.mot_page_button: Button = Button(label="MOT Detail", style=ButtonStyle.secondary)

        # Assign callbacks
        # Type check complains "Cannot assign to a method", and yet here I am doing it. Checkmate.
        self.main_page_button.callback = self.show_main_page  # type: ignore
        self.mot_page_button.callback = self.show_mot_page  # type: ignore

        # Start with the "Main Info" button removed
        self.add_item(self.mot_page_button)

    async def on_timeout(self) -> None:
        for item in self.children:
            if hasattr(item, "disabled"):
                item.disabled = True  # type: ignore
            else:
                log.error(f"Button {item} has no 'disabled' attribute")
        await self.interaction.edit(view=self)

    async def show_main_page(self, interaction: Interaction) -> None:
        embed = await gen_main_embed(self.vehicle_data)
        self.update_buttons(remove="main")
        await interaction.response.edit_message(embed=embed, view=self)
        self.interaction = await interaction.original_response()

    async def show_mot_page(self, interaction: Interaction) -> None:
        embed = await gen_mot_embed(self.vehicle_data)
        self.update_buttons(remove="mot")
        await interaction.response.edit_message(embed=embed, view=self)
        self.interaction = await interaction.original_response()

    def update_buttons(self, remove: str) -> None:
        """Helper function to update buttons based on the current view"""
        self.clear_items()
        if remove != "main":
            self.add_item(self.main_page_button)
        if remove != "mot":
            self.add_item(self.mot_page_button)


class VehicleInfo(commands.Cog):
    """Vehicle Info"""

    def __init__(self, bot: Red):
        self.bot = bot
        self.config = Config.get_conf(self, identifier=2318468588944243)

        self._register_default_configs()
        self.power_unit_strings = ", ".join([e.value for e in PowerUnits])
        self.torque_unit_strings = ", ".join([e.value for e in TorqueUnits])

    def _register_default_configs(self) -> None:
        """Registers default configuration values"""
        self.config.register_user(power_unit=None, torque_unit=None)
        self.config.register_guild(power_unit=None, torque_unit=None)
        self.config.register_global(
            power_unit=PowerUnits.BHP.value,
            torque_unit=TorqueUnits.LB_FT.value,
            vehicles=[],
            additional_vehicle_info_api={"base_url": "", "user_agent": ""},
        )

    vehicle_info_group = app_commands.Group(name="vehicle_info", description="Vehicle Info desc")

    @app_commands.command(name="car")
    async def vehicle_info(self, interaction: Interaction, vrn: str) -> None:
        """Get vehicle information"""
        await interaction.response.defer(thinking=True)

        dvla_ves_token = await self.bot.get_shared_api_tokens("dvla")
        dvsa_mot_history_token = await self.bot.get_shared_api_tokens("dvsa")
        additional_vehicle_info_api_cfg = await self.config.additional_vehicle_info_api()

        try:
            vehicle_data = await fetch_vehicle_data(
                vrn, dvla_ves_token, dvsa_mot_history_token, additional_vehicle_info_api_cfg
            )

            if vehicle_data:
                embed = await gen_main_embed(vehicle_data)
                await interaction.followup.send(embed=embed, view=Buttons(await interaction.original_response(), vehicle_data))

            else:
                await self._send_error_message(interaction, f"Bad request - Registration **{vrn.upper()}** likely invalid.")
        except Exception as e:
            log.exception(e)
            await self._send_error_message(interaction, "Failed to get vehicle info. Check console or logs for details")

    async def _send_error_message(self, interaction: Interaction, message: str) -> None:
        """Helper method to send an error message embed"""
        embed = Embed(title="Error", description=message, colour=Colour.red())
        await interaction.followup.send(embed=embed)

    @commands.group(name="vehicle_info")
    async def vehicle_info_config(self, ctx: commands.Context) -> None:
        """Vehicle info configuration"""
        pass

    @commands.is_owner()
    @vehicle_info_config.group(name="additional_vehicle_info_config")
    async def additional_vehicle_info_api_config(self, ctx: commands.Context) -> None:
        """Manage additional vehicle info API configuration"""
        pass

    @additional_vehicle_info_api_config.command(name="show")
    async def show_additional_vehicle_info_api_config(self, ctx: commands.Context) -> None:
        """Show current additional vehicle info API configuration"""
        embed = Embed(title="Vehicle Info Config", colour=await ctx.embed_colour())
        config = await self.config.additional_vehicle_info_api()

        base_url = config.get(
            "base_url", "Not set. Must be set in order to gather additional vehicle info such as model, VIN, etc."
        )
        user_agent = config.get("user_agent", "Not set. Advised to set for the benefit of the API's webmaster.")

        embed.add_field(name="Base URL", value=base_url, inline=False)
        embed.add_field(name="User Agent", value=user_agent, inline=False)

        await ctx.send(embed=embed)

    @additional_vehicle_info_api_config.command(name="base_url")
    async def set_additional_vehicle_info_api_base_url(self, ctx: commands.Context, url: str) -> None:
        """Set the additional vehicle info API base URL"""
        await self.config.set_raw("additional_vehicle_info_api", "base_url", value=url)
        await ctx.tick()

    @additional_vehicle_info_api_config.command(name="user_agent")
    async def set_additional_vehicle_info_api_user_agent(
        self, ctx: commands.Context, user_agent: str, *args, **kwargs
    ) -> None:
        """Set the additional vehicle info request user agent"""
        user_agent = " ".join([user_agent, *list(args), *list(kwargs.values())])
        await self.config.set_raw("additional_vehicle_info_api", "user_agent", value=user_agent)
        await ctx.tick()

    @vehicle_info_config.group()
    async def user_config(self, ctx: commands.Context) -> None:
        """User configuration"""
        pass

    @user_config.command(name="show")
    async def show_user_config(self, ctx: commands.Context) -> None:
        """Show current user configuration"""
        embed = await config_utils.gen_unit_config_embed(self.config, await ctx.embed_colour(), ctx.author)
        await ctx.send(embed=embed)

    @user_config.command(name="power_unit")
    async def set_user_power_unit(self, ctx: commands.Context, unit: str) -> None:
        """Set the user power unit"""
        try:
            await config_utils.set_power_unit(self.config, ctx.author, unit)
        except ValueError as e:
            await ctx.send(e)
        await ctx.tick()

    @user_config.command(name="torque_unit")
    async def set_user_torque_unit(self, ctx: commands.Context, unit: str) -> None:
        """Set the user torque unit"""
        try:
            await config_utils.set_torque_unit(self.config, ctx.author, unit)
        except ValueError as e:
            await ctx.send(e)
        await ctx.tick()

    @commands.guild_only()
    @vehicle_info_config.group()
    async def guild_config(self, ctx: commands.Context) -> None:
        """Guild configuration"""
        pass

    @guild_config.command(name="show")
    async def show_guild_config(self, ctx: commands.Context) -> None:
        """Show current guild configuration"""
        embed = await config_utils.gen_unit_config_embed(self.config, await ctx.embed_colour(), ctx.guild)  # type: ignore
        await ctx.send(embed=embed)

    @guild_config.command(name="power_unit")
    async def set_guild_power_unit(self, ctx: commands.Context, unit: str) -> None:
        """Set the guild power unit"""
        try:
            await config_utils.set_power_unit(self.config, ctx.guild, unit)  # type: ignore
        except ValueError as e:
            await ctx.send(e)
        await ctx.tick()

    @guild_config.command(name="torque_unit")
    async def set_guild_torque_unit(self, ctx: commands.Context, unit: str) -> None:
        """Set the guild torque unit"""
        try:
            await config_utils.set_torque_unit(self.config, ctx.guild, unit)  # type: ignore
        except ValueError as e:
            await ctx.send(e)
        await ctx.tick()

    @commands.is_owner()
    @vehicle_info_config.group()
    async def global_config(self, ctx: commands.Context) -> None:
        """Global configuration"""
        pass

    @global_config.command(name="show")
    async def show_global_config(self, ctx: commands.Context) -> None:
        """Show current global configuration"""
        embed = await config_utils.gen_unit_config_embed(self.config, await ctx.embed_colour(), "global")
        await ctx.send(embed=embed)

    @global_config.command(name="power_unit")
    async def set_global_power_unit(self, ctx: commands.Context, unit: str) -> None:
        """Set the global power unit"""
        try:
            await config_utils.set_power_unit(self.config, ctx.author, unit)
        except ValueError as e:
            await ctx.send(e)
        await ctx.tick()

    @global_config.command(name="torque_unit")
    async def set_global_torque_unit(self, ctx: commands.Context, unit: str) -> None:
        """Set the global torque unit"""
        try:
            await config_utils.set_torque_unit(self.config, ctx.author, unit)
        except ValueError as e:
            await ctx.send(e)
        await ctx.tick()
