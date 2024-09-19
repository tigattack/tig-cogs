from typing import Literal, Union

from celtic_tuning import PowerUnits, TorqueUnits, resolve_unit_case
from discord import Colour, Embed, Guild, User
from discord.abc import User as UserABC
from redbot.core import Config


async def gen_unit_config_embed(
    config: Config, embed_colour: Colour, entity: Union[UserABC, Guild, Literal["global"]]
) -> Embed:
    """Helper method to send a configuration embed"""
    embed = Embed(
        title="Vehicle Info Config",
        colour=embed_colour,
    )

    this_config = await get_config(config, entity)

    if this_config.get("power_unit"):
        embed.add_field(name="Power Unit", value=this_config.get("power_unit"))
    else:
        global_power_unit = await config.power_unit()
        embed.add_field(
            name="Power Unit",
            value=f"Not set. Will use first found value in order of user, guild, then global ({global_power_unit}) config.",
            inline=False,
        )

    if this_config.get("torque_unit"):
        embed.add_field(name="Torque Unit", value=this_config.get("torque_unit"))
    else:
        global_torque_unit = await config.torque_unit()
        embed.add_field(
            name="Torque Unit",
            value=f"Not set. Will use first found value in order of user, guild, then global ({global_torque_unit}) config.",
            inline=False,
        )

    return embed


async def set_power_unit(config: Config, entity: UserABC | Guild, unit: str) -> None:
    """Helper method to set the power unit config value"""
    unit_normalised = resolve_unit_case(unit, PowerUnits)

    if unit_normalised not in PowerUnits._value2member_map_:
        valid_units = ", ".join([pu.value for pu in PowerUnits])
        raise ValueError(f"Invalid power unit. Valid options are: {valid_units}.")

    await set_config(config, entity, "power_unit", unit_normalised)


async def set_torque_unit(config: Config, entity: UserABC | Guild, unit: str) -> None:
    """Helper method to set the torque unit config value"""
    unit_normalised = resolve_unit_case(unit, TorqueUnits)

    if unit_normalised not in TorqueUnits._value2member_map_:
        valid_units = ", ".join([tu.value for tu in TorqueUnits])
        raise ValueError(f"Invalid torque unit. Valid options are: {valid_units}.")

    await set_config(config, entity, "torque_unit", unit_normalised)


async def get_config(config: Config, entity: UserABC | Guild | Literal["global"]) -> dict:
    """Get the config for a user or guild"""
    if isinstance(entity, User):
        return await config.user(entity).all()
    elif isinstance(entity, Guild):
        return await config.guild(entity).all()
    elif entity == "global":
        return await config.all()
    return {}


async def set_config(config: Config, entity: UserABC | Guild | Literal["global"], key: str, value: str) -> None:
    """Set a config value for a user or guild"""
    if isinstance(entity, User):
        await config.user(entity).set_raw(key, value=value)
    elif isinstance(entity, Guild):
        await config.guild(entity).set_raw(key, value=value)
    elif entity == "global":
        # TODO: this doesn't work
        await config.set_raw(key, value=value)
