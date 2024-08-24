import logging
from typing import Literal, Optional

from CelticTuning import Celtic, PowerUnits, TorqueUnits
from discord import ButtonStyle, Colour, Embed, Guild, Interaction, InteractionMessage, User
from discord.abc import User as UserABC
from discord.ui import Button, View
from redbot.core import Config, app_commands, commands
from redbot.core.bot import Red

from .models import VehicleData
from .utils import gen_mot_embed, gen_vehicle_embed, get_vehicle_info

log = logging.getLogger("red.tigattack.vehicle_info")


class Buttons(View):
    def __init__(self, interaction: InteractionMessage, vehicle_data: VehicleData, *, timeout: float = 180):
        super().__init__(timeout=timeout)
        self.vehicle_data = vehicle_data

        self.current_embed: Optional[Embed] = None
        self.interaction = interaction

        # Initial button setup: Start with "Main Info" disabled
        self.main_info_button: Button = Button(label="Main Info", style=ButtonStyle.primary)
        self.mot_info_button: Button = Button(label="Extended MOT Info", style=ButtonStyle.secondary)

        # Assign callbacks
        # Type check complains "Cannot assign to a method", and yet here I am doing it. Checkmate.
        self.main_info_button.callback = self.show_main_info  # type: ignore
        self.mot_info_button.callback = self.show_mot_info  # type: ignore

        # Start with the "Main Info" button removed
        self.add_item(self.mot_info_button)

    async def on_timeout(self) -> None:
        for i in self.children:
            # Type check complains type has no attribute disabled, and yet here it is working ¯\_(ツ)_/¯
            i.disabled = True  # type: ignore
        await self.interaction.edit(view=self)

    async def show_main_info(self, interaction: Interaction):
        # Generate main vehicle info embed
        embed = await gen_vehicle_embed(self.vehicle_data)

        # Remove all buttons and add back only the necessary ones
        self.clear_items()
        self.add_item(self.mot_info_button)

        await interaction.response.edit_message(embed=embed, view=self)
        self.interaction = await interaction.original_response()

    async def show_mot_info(self, interaction: Interaction):
        # Generate MOT info embed
        embed = await gen_mot_embed(self.vehicle_data)

        # Remove all buttons and add back only the necessary ones
        self.clear_items()
        self.add_item(self.main_info_button)

        await interaction.response.edit_message(embed=embed, view=self)
        self.interaction = await interaction.original_response()


class VehicleInfo(commands.Cog):
    """Vehicle Info"""

    def __init__(self, bot: Red):
        self.bot = bot
        self.config = Config.get_conf(self, identifier=2318468588944243)

        default_user_config = {
            "power_unit": None,
            "torque_unit": None,
        }

        default_guild_config = {
            "power_unit": None,
            "torque_unit": None,
        }

        default_global_config = {
            "power_unit": PowerUnits.BHP.value,
            "torque_unit": TorqueUnits.LB_FT.value,
            "vehicles": [],
            "additional_vehicle_info_api": {
                "base_url": "",
                "user_agent": "",
            },
        }

        self.config.register_user(**default_user_config)
        self.config.register_guild(**default_guild_config)
        self.config.register_global(**default_global_config)

        self.power_unit_strings = ", ".join([e.value for e in PowerUnits])
        self.torque_unit_strings = ", ".join([e.value for e in TorqueUnits])

    vehicle_info_group = app_commands.Group(name="vehicle_info", description="Vehicle Info desc")

    @app_commands.command(name="car")
    async def vehicle_info(self, interaction: Interaction, vrn: str) -> None:
        """Vehicle info commands"""
        await interaction.response.defer(thinking=True)

        dvla_ves_token = await self.bot.get_shared_api_tokens("dvla")
        dvsa_mot_history_token = await self.bot.get_shared_api_tokens("dvsa")
        additional_vehicle_info_api_cfg = await self.config.additional_vehicle_info_api()

        try:
            vehicle_data = await get_vehicle_info(vrn, dvla_ves_token, dvsa_mot_history_token, additional_vehicle_info_api_cfg)

            if vehicle_data:
                embed = await gen_vehicle_embed(vehicle_data)
                await interaction.followup.send(embed=embed, view=Buttons(await interaction.original_response(), vehicle_data))

            else:
                await interaction.followup.send(
                    embed=Embed(
                        title="Error Querying Vehicle",
                        description=f"Bad request - Registration **{vrn.upper()}** likely invalid.",
                        colour=Colour.red(),
                    )
                )
        except Exception as e:
            log.exception(e)
            await interaction.followup.send(
                embed=Embed(
                    title="Error",
                    description="Failed to get vehicle info. Check console or logs for details",
                    colour=Colour.red(),
                )
            )

    @commands.group(name="vehicle_info")
    async def vehicle_info_config(self, ctx: commands.Context) -> None:
        """Vehicle info commands"""
        pass

    @commands.is_owner()
    @vehicle_info_config.group(name="additional_vehicle_info_config")
    async def additional_vehicle_info_api_config(self, ctx: commands.Context) -> None:
        """Additional vehicle info API config"""
        pass

    @additional_vehicle_info_api_config.command(name="show")
    async def show_additional_vehicle_info_api_config(self, ctx: commands.Context) -> None:
        """Show current additional vehicle info config"""
        embed = Embed(
            title="Vehicle Info Config",
            colour=await ctx.embed_colour(),
        )

        config = await self.config.additional_vehicle_info_api()
        base_url = config.get("base_url")
        user_agent = config.get("user_agent")

        if base_url:
            embed.add_field(name="Base URL", value=base_url)
        else:
            embed.add_field(
                name="Base URL",
                value="Not set. Must be set in order to gather additional vehicle info such as model, VIN, etc.",
                inline=False,
            )

        if user_agent:
            embed.add_field(name="User Agent", value=user_agent)
        else:
            embed.add_field(
                name="User Agent",
                value="Not set. Advised to set for the benefit of the API's webmaster.",
                inline=False,
            )
        await ctx.send(embed=embed)

    @additional_vehicle_info_api_config.command(name="base_url")
    async def set_additional_vehicle_info_api_base_url(self, ctx: commands.Context, url: str) -> None:
        """Set the additional vehicle info api base url"""
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
        """User config"""
        pass

    @user_config.command(name="show")
    async def show_user_config(self, ctx: commands.Context) -> None:
        """Show current user config"""
        config = await self._get_config(ctx.author)
        embed = await self._gen_unit_config_embed(await ctx.embed_colour(), config)
        await ctx.send(embed=embed)

    @user_config.command(name="power_unit")
    async def set_user_power_unit(self, ctx: commands.Context, unit: str) -> None:
        """Set the user power unit"""
        await self._set_power_unit(ctx, ctx.author, unit)

    @user_config.command(name="torque_unit")
    async def set_user_torque_unit(self, ctx: commands.Context, unit: str) -> None:
        """Set the user torque unit"""
        await self._set_torque_unit(ctx, ctx.author, unit)

    @commands.guild_only()
    @vehicle_info_config.group()
    async def guild_config(self, ctx: commands.Context) -> None:
        """Guild config"""
        pass

    @guild_config.command(name="show")
    async def show_guild_config(self, ctx: commands.Context) -> None:
        """Show current guild config"""
        config = await self._get_config(ctx.guild)  # type: ignore
        embed = await self._gen_unit_config_embed(await ctx.embed_colour(), config)
        await ctx.send(embed=embed)

    @guild_config.command(name="power_unit")
    async def set_guild_power_unit(self, ctx: commands.Context, unit: str) -> None:
        """Set the guild power unit"""
        await self._set_power_unit(ctx, ctx.guild, unit)  # type: ignore

    @guild_config.command(name="torque_unit")
    async def set_guild_torque_unit(self, ctx: commands.Context, unit: str) -> None:
        """Set the guild torque unit"""
        await self._set_torque_unit(ctx, ctx.guild, unit)  # type: ignore

    @commands.is_owner()
    @vehicle_info_config.group()
    async def global_config(self, ctx: commands.Context) -> None:
        """Global config"""
        pass

    @global_config.command(name="show")
    async def show_global_config(self, ctx: commands.Context) -> None:
        """Show current global config"""
        config = await self._get_config("global")
        embed = await self._gen_unit_config_embed(await ctx.embed_colour(), config)
        await ctx.send(embed=embed)

    @global_config.command(name="power_unit")
    async def set_global_power_unit(self, ctx: commands.Context, unit: str) -> None:
        """Set the global power unit"""
        await self._set_power_unit(ctx, ctx.author, unit)

    @global_config.command(name="torque_unit")
    async def set_global_torque_unit(self, ctx: commands.Context, unit: str) -> None:
        """Set the global torque unit"""
        await self._set_torque_unit(ctx, ctx.author, unit)

    async def _gen_unit_config_embed(self, embed_colour: Colour, config: dict) -> Embed:
        """Helper method to send a configuration embed"""
        embed = Embed(
            title="Vehicle Info Config",
            colour=embed_colour,
        )

        if config.get("power_unit"):
            embed.add_field(name="Power Unit", value=config.get("power_unit"))
        else:
            global_power_unit = await self.config.power_unit()
            embed.add_field(
                name="Power Unit",
                value="Not set. Will use first found value in order of user, "
                + f"guild, then global ({global_power_unit}) config.",
                inline=False,
            )

        if config.get("torque_unit"):
            embed.add_field(name="Torque Unit", value=config.get("torque_unit"))
        else:
            global_torque_unit = await self.config.torque_unit()
            embed.add_field(
                name="Torque Unit",
                value="Not set. Will use first found value in order of user, "
                + f"guild, then global ({global_torque_unit}) config.",
                inline=False,
            )

        return embed

    async def _get_config(self, entity: UserABC | Guild | Literal["global"]) -> dict:
        """Get the config for a user or guild"""
        if isinstance(entity, User):
            return await self.config.user(entity).all()
        elif isinstance(entity, Guild):
            return await self.config.guild(entity).all()
        elif entity == "global":
            return await self.config.all()
        return {}

    async def _set_config(self, entity: UserABC | Guild | Literal["global"], key: str, value: str):
        """Set a config value for a user or guild"""
        if isinstance(entity, User):
            await self.config.user(entity).set_raw(key, value=value)
        elif isinstance(entity, Guild):
            await self.config.guild(entity).set_raw(key, value=value)
        elif entity == "global":
            await self.config.set_raw(key, value=value)  # TODO: this doesn't work

    async def _set_power_unit(self, ctx: commands.Context, entity: UserABC | Guild, unit: str):
        """Helper method to set the power unit config value"""
        unit_normalised = Celtic.normalise_unit(unit, PowerUnits)
        if unit_normalised not in PowerUnits._value2member_map_:
            valid_units = ", ".join([pu.value for pu in PowerUnits])
            await ctx.send(
                f"Invalid power unit. Valid options are: {valid_units}."
            )  # TODO: why does this send, should just raise
            return
        await self._set_config(entity, "power_unit", unit_normalised)
        await ctx.tick()

    async def _set_torque_unit(self, ctx: commands.Context, entity: UserABC | Guild, unit: str):
        """Helper method to set the torque unit config value"""
        unit_normalised = Celtic.normalise_unit(unit, TorqueUnits)
        if unit_normalised not in TorqueUnits._value2member_map_:
            valid_units = ", ".join([tu.value for tu in TorqueUnits])
            await ctx.send(
                f"Invalid torque unit. Valid options are: {valid_units}."
            )  # TODO: why does this send, should just raise
            return
        await self._set_config(entity, "torque_unit", unit_normalised)
        await ctx.tick()
