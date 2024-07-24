from redbot.core.bot import Red

from .events_manager import EventsManager


async def setup(bot: Red):
    await bot.add_cog(EventsManager(bot))
