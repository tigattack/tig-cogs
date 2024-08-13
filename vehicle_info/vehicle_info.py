import logging
import re
from datetime import datetime
from enum import Enum
from typing import Literal, Optional

import aiohttp
import discord
from CelticTuning import Celtic, PowerUnits, TorqueUnits
from redbot.core import Config, app_commands, checks, commands, utils
from redbot.core.bot import Red

from .additional_vehicle_info import VehicleDetails, VehicleLookupAPI
from .dvla_ves import Vehicle, VehicleEnquiryAPI

log = logging.getLogger("red.tigattack.vehicle_info")


class VehicleColours(Enum):
    r"""
    Vehicle colours used by the DVLA

    Colours sourced from:
    https://hmvf.co.uk/topic/23542-dvla-vehicle-basic-colours-to-cover-the-manufacturer%E2%80%99s-description/
    Couldn't find any better source ¯\\_(ツ)_/¯
    """
    BEIGE = 0xf5f5dc
    BLACK = 0x000000
    BLUE = 0x0000ff
    BRONZE = 0xcd7f32
    BROWN = 0x8b4513
    CREAM = 0xfffcdc
    GREEN = 0x008000
    GREY = 0x808080
    GOLD = 0xffd700
    MAROON = 0x800000
    ORANGE = 0xffa500
    PINK = 0xff1493
    PURPLE = 0x800080
    RED = 0xff0000
    SILVER = 0xc0c0c0
    TURQUOISE = 0x40e0d0
    WHITE = 0xffffff
    YELLOW = 0xffff00

    @classmethod
    def get_colour(cls, colour_name: Optional[str]) -> int:
        """Get the colour value by its name, case-insensitively."""
        if colour_name:
            colour_name = colour_name.upper()
            for colour in cls:
                if colour_name == colour.name:
                    return colour.value
        return cls.GREY.value


async def fetch_get(url_in: str, headers: dict = {}, data: dict = {}) -> dict:
    """Make web requests"""
    async with aiohttp.request("GET", url_in, headers=headers, data=data) as response:
        if response.status != 200:  # noqa: PLR2004
            return {}
        return await response.json()


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

    def _check_if_owner(interaction: discord.Interaction, owner_ids: list) -> bool:
        if owner_ids:
            return interaction.user.id in owner_ids
        raise KeyError("Owner IDs not found")

    async def vehicle_info(self, interaction: discord.Interaction, vrn: str):
        """Vehicle info commands"""
        embed = await self._get_vehicle_info(vrn)
        await ctx.send(embed=embed)

    @app_commands.check(_check_if_owner)
    @vehicle_info_group.command(name="additional_vehicle_info_config")
    async def additional_vehicle_info_api_config(self, interaction: discord.Interaction):
        """Additional vehicle info API config"""
        pass

    @additional_vehicle_info_api_config.command(name="show")
    async def show_additional_vehicle_info_api_config(self, ctx: commands.Context):
        """Show current additional vehicle info config"""
        embed = discord.Embed(
            title="Vehicle Info Config",
            colour=await ctx.embed_colour(),
        )

        config = await self.config.additional_vehicle_info_api()
        base_url = config.get('base_url')
        user_agent = config.get('user_agent')

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
    async def set_additional_vehicle_info_api_base_url(self, ctx: commands.Context, url: str):
        """Set the additional vehicle info api base url"""
        await self.config.set_raw("additional_vehicle_info_api", "base_url", value=url)
        await ctx.tick()

    @additional_vehicle_info_api_config.command(name="user_agent")
    async def set_additional_vehicle_info_api_user_agent(self, ctx: commands.Context, user_agent: str, *args, **kwargs):
        """Set the additional vehicle info request user agent"""
        user_agent = " ".join([user_agent, *list(args), *list(kwargs.values())])
        await self.config.set_raw("additional_vehicle_info_api", "user_agent", value=user_agent)
        await ctx.tick()

    @vehicle_info.group()
    async def user_config(self, ctx: commands.Context):
        """User config"""
        pass

    @user_config.command(name="show")
    async def show_user_config(self, ctx: commands.Context):
        """Show current user config"""
        config = await self._get_config(ctx.author)
        embed = await self._gen_unit_config_embed(await ctx.embed_colour(), config)
        await ctx.send(embed=embed)

    @user_config.command(name="power_unit")
    async def set_user_power_unit(self, ctx: commands.Context, unit: str):
        """Set the user power unit"""
        await self._set_power_unit(ctx, ctx.author, unit)

    @user_config.command(name="torque_unit")
    async def set_user_torque_unit(self, ctx: commands.Context, unit: str):
        """Set the user torque unit"""
        await self._set_torque_unit(ctx, ctx.author, unit)

    @commands.guild_only()
    @vehicle_info.group()
    async def guild_config(self, ctx: commands.Context):
        """Guild config"""
        pass

    @guild_config.command(name="show")
    async def show_guild_config(self, ctx: commands.Context):
        """Show current guild config"""
        config = await self._get_config(ctx.guild)  # type: ignore
        embed = await self._gen_unit_config_embed(await ctx.embed_colour(), config)
        await ctx.send(embed=embed)

    @guild_config.command(name="power_unit")
    async def set_guild_power_unit(self, ctx: commands.Context, unit: str):
        """Set the guild power unit"""
        await self._set_power_unit(ctx, ctx.guild, unit)  # type: ignore

    @guild_config.command(name="torque_unit")
    async def set_guild_torque_unit(self, ctx: commands.Context, unit: str):
        """Set the guild torque unit"""
        await self._set_torque_unit(ctx, ctx.guild, unit)  # type: ignore

    @commands.is_owner()
    @vehicle_info.group()
    async def global_config(self, ctx: commands.Context):
        """Global config"""
        pass

    @global_config.command(name="show")
    async def show_global_config(self, ctx: commands.Context):
        """Show current global config"""
        config = await self._get_config("global")
        embed = await self._gen_unit_config_embed(await ctx.embed_colour(), config)
        await ctx.send(embed=embed)

    @global_config.command(name="power_unit")
    async def set_global_power_unit(self, ctx: commands.Context, unit: str):
        """Set the global power unit"""
        await self._set_power_unit(ctx, ctx.author, unit)

    @global_config.command(name="torque_unit")
    async def set_global_torque_unit(self, ctx: commands.Context, unit: str):
        """Set the global torque unit"""
        await self._set_torque_unit(ctx, ctx.author, unit)

    async def _gen_unit_config_embed(self, embed_colour: discord.Colour, config: dict) -> discord.Embed:
        """Helper method to send a configuration embed"""
        embed = discord.Embed(
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

    async def _get_config(self, entity: discord.abc.User | discord.Guild | Literal["global"]) -> dict:
        """Get the config for a user or guild"""
        if isinstance(entity, discord.User):
            return await self.config.user(entity).all()
        elif isinstance(entity, discord.Guild):
            return await self.config.guild(entity).all()
        elif entity == "global":
            return await self.config.all()
        return {}

    async def _set_config(self, entity: discord.abc.User | discord.Guild | Literal["global"], key: str, value: str):
        """Set a config value for a user or guild"""
        if isinstance(entity, discord.User):
            await self.config.user(entity).set_raw(key, value=value)
        elif isinstance(entity, discord.Guild):
            await self.config.guild(entity).set_raw(key, value=value)
        elif entity == "global":
            await self.config.set_raw(key, value=value) # TODO: this doesn't work

    async def _set_power_unit(self, ctx: commands.Context, entity: discord.abc.User | discord.Guild, unit: str):
        """Helper method to set the power unit config value"""
        unit_normalised = Celtic.normalise_unit(unit, PowerUnits)
        if unit_normalised not in PowerUnits._value2member_map_:
            valid_units = ", ".join([pu.value for pu in PowerUnits])
            await ctx.send(f"Invalid power unit. Valid options are: {valid_units}.") # TODO: why does this send, should just raise
            return
        await self._set_config(entity, "power_unit", unit_normalised)
        await ctx.tick()

    async def _set_torque_unit(self, ctx: commands.Context, entity: discord.abc.User | discord.Guild, unit: str):
        """Helper method to set the torque unit config value"""
        unit_normalised = Celtic.normalise_unit(unit, TorqueUnits)
        if unit_normalised not in TorqueUnits._value2member_map_:
            valid_units = ", ".join([tu.value for tu in TorqueUnits])
            await ctx.send(f"Invalid torque unit. Valid options are: {valid_units}.") # TODO: why does this send, should just raise
            return
        await self._set_config(entity, "torque_unit", unit_normalised)
        await ctx.tick()

    async def _get_vehicle_info(self, vrn: str):
        """Get vehicle info"""
        dvla_token = await self.bot.get_shared_api_tokens("dvla")

        if dvla_token.get("token") is None:
            raise ValueError("DVLA token not found")

        api = VehicleEnquiryAPI(dvla_token["token"])
        ves_info = await api.get_vehicle(vrn)

        async with self.config.all() as config:
            if config["additional_vehicle_info_api"].get("base_url"):
                additional_info_api = VehicleLookupAPI(
                    config["additional_vehicle_info_api"]["base_url"],
                    config["additional_vehicle_info_api"].get("user_agent"),
                )
                additional_info = await additional_info_api.get_vehicle_details(vrn)
            else:
                additional_info = None

        embed = self._gen_vehicle_embed(ves_info, additional_info)

        return embed

    @staticmethod
    async def _get_vehicle_remap_estimate(vrn: str):
        """Get vehicle remap estimate"""
        ct = Celtic(vrn)
        remap = ct.remap_data()

        # TODO: build embed

        return remap

    def _gen_vehicle_embed(self, ves_info: Vehicle, additional_info: Optional[VehicleDetails]):  # noqa: PLR0912, PLR0915
        """Helper method to send a vehicle embed"""

        # Set some basic values
        colour_hex = VehicleColours.get_colour(ves_info.colour)
        vehicle_is_ev = str(ves_info.fuelType).lower() == "electricity"

        # Set some Discord-specific strings with emojis, timestamps, etc. to be used in the embed
        fuel_label = (
            "Fuel \U000026FD" if str(ves_info.fuelType).lower() in ["petrol", "diesel"]
            else "Fuel \U000026FD\U000026A1" if str(ves_info.fuelType).lower() == "hybrid electric"
            else "Fuel \U000026A1" if vehicle_is_ev
            else "Fuel"
        )
        if ves_info.motStatus == "Valid":
            mot_status = utils.chat_formatting.success(ves_info.motStatus)
        elif ves_info.motStatus == "Not valid":
            mot_status = utils.chat_formatting.error(ves_info.motStatus)
        else:
            mot_status = ves_info.motStatus  # type: ignore

        if ves_info.taxStatus == "Taxed":
            tax_status = utils.chat_formatting.success(ves_info.taxStatus)
        else:
            tax_status = utils.chat_formatting.error(str(ves_info.taxStatus))

        if ves_info.motExpiryDate:
            delta = datetime.strptime(ves_info.motExpiryDate, "%Y-%m-%d")
            mot_expiry_timestamp = discord.utils.format_dt(delta, "R")
        else:
            mot_expiry_timestamp = None

        if ves_info.monthOfFirstDvlaRegistration:
            delta = datetime.strptime(ves_info.monthOfFirstDvlaRegistration, "%Y-%m")
            month_of_first_uk_registration_timestamp = discord.utils.format_dt(delta, "d")
        else:
            month_of_first_uk_registration_timestamp = None

        if ves_info.monthOfFirstRegistration:
            delta = datetime.strptime(ves_info.monthOfFirstRegistration, "%Y-%m")
            month_of_first_registration_timestamp = discord.utils.format_dt(delta, "d")
        else:
            month_of_first_registration_timestamp = None

        if ves_info.taxDueDate:
            delta = datetime.strptime(ves_info.taxDueDate, "%Y-%m-%d")
            tax_due_timestamp = discord.utils.format_dt(delta, "R")
        else:
            tax_due_timestamp = None

        if ves_info.dateOfLastV5CIssued:
            delta = datetime.strptime(ves_info.dateOfLastV5CIssued, "%Y-%m-%d")
            date_of_last_v5c_issued_timestamp = discord.utils.format_dt(delta, "R")
        else:
            date_of_last_v5c_issued_timestamp = None

        # Create the embed and add fields
        embed = discord.Embed(colour=colour_hex)

        embed.add_field(name="Colour", value=str(ves_info.colour).title(), inline=True)
        embed.add_field(name=fuel_label, value=str(ves_info.fuelType).title(), inline=True)

        if not vehicle_is_ev:
            embed.add_field(name="Engine Capacity", value=f"{ves_info.engineCapacity}cc", inline=True)

        embed.add_field(name="First Registered", value=month_of_first_registration_timestamp, inline=True)
        if (
            ves_info.monthOfFirstRegistration != ves_info.monthOfFirstDvlaRegistration
            and ves_info.monthOfFirstDvlaRegistration
        ):
            embed.add_field(name="First Registered in UK", value=month_of_first_uk_registration_timestamp, inline=True)

        embed.add_field(name="V5C Last Issued", value=date_of_last_v5c_issued_timestamp, inline=True)

        if not vehicle_is_ev:
            if ves_info.realDrivingEmissions:
                embed.add_field(name="Real Driving Emissions", value=ves_info.realDrivingEmissions, inline=True)

            if ves_info.co2Emissions:
                embed.add_field(name="CO₂ Emissions", value=f"{ves_info.co2Emissions}g/km", inline=True)

        if ves_info.euroStatus:
            embed.add_field(name="Euro Status", value=ves_info.euroStatus, inline=True)

        embed.add_field(name="Tax Status", value=tax_status, inline=True)
        if ves_info.taxStatus != "SORN":
            embed.add_field(name="Tax Expiry", value=tax_due_timestamp, inline=True)

        embed.add_field(name="MOT Status", value=mot_status, inline=True)
        if ves_info.motStatus not in ["No details held by DVLA", "No results returned"]:
            embed.add_field(name="MOT Expiry", value=mot_expiry_timestamp, inline=True)

        if ves_info.automatedVehicle is not None:
            embed.add_field(name="Automated Vehicle", value=ves_info.automatedVehicle, inline=True)

        if additional_info:
            embed.title = (
                f"{ves_info.registrationNumber.upper()} | {ves_info.make} {additional_info.Model}"
            )
            embed.add_field(name="VIN", value=additional_info.VIN, inline=True)
            field_count = 0
            for field in embed.fields:
                if field.name == "First Registered in UK":
                    delta = datetime.strptime(additional_info.Year, "%d/%m/%Y")
                    embed.set_field_at(
                        index=field_count, name="First Registered in UK", value=discord.utils.format_dt(delta, "d")
                    )
                elif field.name == "First Registered":
                    delta = datetime.strptime(additional_info.Year, "%d/%m/%Y")
                    embed.set_field_at(index=field_count, name="First Registered", value=discord.utils.format_dt(delta, "d"))
                field_count += 1
        else:
            embed.title = f"{ves_info.registrationNumber.upper()} | {ves_info.make}"
            embed.set_footer(
                text="Additional info such as model, VIN, etc. not available. "
                + "Check `[p]vehicle_info additional_vehicle_info_config`."
            )

        return embed
