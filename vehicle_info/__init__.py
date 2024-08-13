from redbot.core.bot import Red

from .vehicle_info import VehicleInfo


async def setup(bot: Red):
    await bot.add_cog(VehicleInfo(bot))
