import datetime
import logging

import discord
from discord.ext import tasks
from redbot.core import Config, checks, commands
from redbot.core.bot import Red

log = logging.getLogger("red.tigattack.events_manager")

class EventsManager(commands.Cog):
    """Events nmanager"""

    def __init__(self, bot):
        self.bot: Red = bot
        self.config = Config.get_conf(cog_instance=self, identifier=1421660776994455)

        default_guild_config = {
            "live_events_category": None,
            "archived_events_category": None,
            "log_channel": None
        }

        self.config.register_guild(**default_guild_config)

    @checks.mod()
    @commands.group()
    async def events(self, ctx):
        pass


    @events.command()
    async def config(self, ctx):
        """Show current config"""
        async with self.config.guild(ctx.guild).all() as config:
            live_cat_conf = config.get("live_events_category")
            archive_cat_conf = config.get("archived_events_category")
            log_channel_conf = config.get("log_channel")

        embed = discord.Embed(
            title="Events Manager Config",
            colour=await ctx.embed_colour(),
        )

        embed.add_field(name="Live Events Category", value=ctx.guild.get_channel(live_cat_conf))
        embed.add_field(name="Archived Events Category", value=ctx.guild.get_channel(archive_cat_conf))
        embed.add_field(name="Log Channel", value=ctx.guild.get_channel(log_channel_conf))

        await ctx.send(embed=embed)


    @events.command()
    async def live_category(self, ctx, category: discord.CategoryChannel):
        """Set the category for live events"""
        await self.config.guild(ctx.guild).live_events_category.set(category.id)
        await ctx.tick()


    @events.command()
    async def archive_category(self, ctx, category: discord.CategoryChannel):
        """Set the category for archived events"""
        await self.config.guild(ctx.guild).archived_events_category.set(category.id)
        await ctx.tick()


    @events.command()
    async def log_channel(self, ctx, channel: discord.TextChannel):# -> Any | None:
        """Set the log channel"""
        # Check if bot can send messages in that channel
        if not channel.permissions_for(ctx.guild.me).send_messages:
            return await ctx.send("I can't send messages in that channel")

        await self.config.guild(ctx.guild).log_channel.set(channel.id)
        await ctx.tick()


    @commands.Cog.listener()
    async def on_scheduled_event_create(self, payload: discord.ScheduledEvent):
        """Create channel and role pairs for scheduled events"""
        guild = payload.guild

        channel_role_name = self.construct_event_name(payload)

        # Create role if it doesn't exist
        if any(role.name == channel_role_name for role in guild.roles):
            log.info("Role %s already exists, skipping creation", channel_role_name)
            role = [role for role in guild.roles if role.name == channel_role_name][0]
        else:
            log.info("Creating role %s", channel_role_name)
            try:
                role = await guild.create_role(name=channel_role_name)
            except discord.errors.Forbidden:
                log.error("Role creation forbidden.")
                await self.send_log_message("`events_manager`: Role creation forbidden.", guild)

        # Add event users to role
        # At this point it should only be the user who created the event but ¯\_(ツ)_/¯
        for user in payload.users:
            await user.add_roles(role)

        # Create channel if it doesn't exist
        if any(channel.name == channel_role_name for channel in guild.text_channels):
            log.info("Channel %s already exists, skipping creation", channel_role_name)
        else:
            log.info("Creating channel %s", channel_role_name)
            category = await self.config.guild(guild).live_events_category()
            try:
                await guild.create_text_channel(
                    name=channel_role_name,
                    category=category,
                    topic=f"{payload.name} in {payload.location} from {payload.start_time.strftime('%H:%M %m/%d/%Y')} " +
                            f"to {payload.end_time.strftime('%H:%M %m/%d/%Y')}")
            except discord.errors.Forbidden:
                log.error("Channel creation forbidden.")
                await self.send_log_message("`events_manager`: Channel creation forbidden.", guild)


    @commands.Cog.listener()
    async def on_scheduled_event_update(self, before: discord.ScheduledEvent, after: discord.ScheduledEvent):
        """Patch channel & role name and metadata when event is updated"""
        guild = before.guild

        old_channel_role_name = self.construct_event_name(before)
        new_channel_role_name = self.construct_event_name(after)

        event_channel = [channel for channel in guild.channels if channel.name == old_channel_role_name][0]
        event_role = [role for role in guild.roles if role.name == old_channel_role_name][0]

        event_role.edit(name=new_channel_role_name)

        event_channel.edit(
            name=new_channel_role_name,
            topic=f"{after.name} in {after.location} from {after.start_time.strftime('%H:%M %m/%d/%Y')} " +
                                    f"to {after.end_time.strftime('%H:%M %m/%d/%Y')}")


    @commands.Cog.listener()
    async def on_scheduled_event_user_add(self, payload: discord.ScheduledEvent, user: discord.User):
        """Add the user to the event role"""
        role_name = self.construct_event_name(payload)
        role = [role for role in payload.guild.roles if role.name == role_name][0]
        member = payload.guild.get_member(user.id)
        await member.add_roles(role)


    @commands.Cog.listener()
    async def on_scheduled_event_user_remove(self, payload: discord.ScheduledEvent, user: discord.User):
        """Remove the user from the event role"""
        role_name = self.construct_event_name(payload)
        role = [role for role in payload.guild.roles if role.name == role_name][0]
        member = payload.guild.get_member(user.id)
        await member.remove_roles(role)


    @tasks.loop(hours=1)
    async def cleanup(self):
        """Move expired events to the archive category"""
        guilds = await self.bot.guilds

        for guild in guilds:
            archive_cat = await self.config.guild(guild).archived_events_category()
            for event in guild.scheduled_events:
                if event.end_time < datetime.datetime.now():
                    channel_role_name = self.construct_event_name(event)
                    channel = [channel for channel in event.guild.channels if channel.name == channel_role_name][0]
                    channel.edit(category=archive_cat)


    async def send_log_message(self, message, guild):
        """Send a message to the log channel"""
        log_channel_id = await self.config.guild(guild).log_channel()
        if log_channel_id:
            log_channel = guild.get_channel(log_channel_id)
            if log_channel:
                return await log_channel.send(message)


    def construct_event_name(self, payload: discord.ScheduledEvent) -> str:
        """Construct a name to be used for channels, roles, etc. based on scheduled event data"""
        event_date_str = payload.start_time.strftime("%d%b").lower()
        return "-".join([payload.name.replace(" ", "-"), payload.location, event_date_str])
