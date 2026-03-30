import re
from datetime import datetime, timedelta
from typing import Optional
from zoneinfo import ZoneInfo

import discord
from discord import app_commands
from discord.ext import commands

from config import DATETIME_FORMAT_1, DATETIME_FORMAT_2
from utils import ephemeral_response
from db import save_raid_to_db
from raid import Raid
from ui.views import RaidManagementView, RaidTemplateSelectView

# =====================================================
# Slash Commands
# =====================================================
@app_commands.command(name="raid", description="Create a raid in this channel.")
@app_commands.describe(
    raid_name="Name of the raid",
    raid_date="Date/time (HH:MM YYYY-MM-DD lub YYYY-MM-DD HH:MM)",
    max_players="Max combined MAIN+ALT",
    allow_alts="Allow user alt sign-ups?",
    max_alts="Max ALTs per user",
    priority="If True, only roles from prioritylist can sign up as MAIN until time_left <= priority_hours",
    prioritylist="Comma-separated list of priority roles, e.g. 'Role1, Role2'",
    priority_hours="Time window (hours) for forced priority. Default = 6",
    description="Description for the raid (displayed under date)",
    required_sps="Comma-separated list, e.g. 'MAG_SP10=2, Arch_SP4=1'",
    timezone="Timezone for the raid, e.g. Europe/Warsaw (default)"
)
async def raid_slash(
        interaction: discord.Interaction,
        raid_name: str = "Unnamed Raid",
        raid_date: str = "2025-01-01 20:00",
        max_players: int = 10,
        allow_alts: bool = False,
        max_alts: int = 0,
        priority: bool = False,
        prioritylist: str = "",
        priority_hours: int = 6,
        description: str = "",
        required_sps: str = "",
        timezone: str = "Europe/Warsaw"
):
    """Create a raid in this channel."""
    bot = interaction.client
    channel_id = interaction.channel_id
    
    if channel_id in bot.raids:
        # Use ephemeral message
        await ephemeral_response(interaction, "A raid is already active in this channel!")
        return
    
    parsed_dt = None
    for fmt in (DATETIME_FORMAT_1, DATETIME_FORMAT_2):
        try:
            naive_dt = datetime.strptime(raid_date, fmt)
            parsed_dt = naive_dt.replace(tzinfo=ZoneInfo(timezone))
            break
        except:
            pass
    
    if not parsed_dt:
        # Use ephemeral message
        await ephemeral_response(interaction, "Could not parse date/time. Use 'HH:MM YYYY-MM-DD' or 'YYYY-MM-DD HH:MM'.")
        return
    
    raid_obj = Raid(
        channel_id=channel_id,
        creator=interaction.user,
        raid_name=raid_name,
        description=description,
        raid_datetime=parsed_dt,
        max_players=max_players,
        allow_alts=allow_alts,
        max_alts=max_alts,
        priority=priority,
        prioritylist=prioritylist,
        priority_hours=priority_hours,
        bot=bot
    )
    
    req_dict = {}
    req_original = {}
    if required_sps.strip():
        segments = required_sps.split(",")
        for seg in segments:
            seg = seg.strip()
            if "=" in seg:
                key, value_str = seg.split("=", 1)
                key = key.strip()
                value_str = value_str.strip()
                if not re.fullmatch(r"[A-Za-z]+_[A-Za-z]+\d+", key):
                    continue
                if not re.fullmatch(r"\d+", value_str):
                    continue
                cnt = int(value_str)
                if cnt < 0:
                    cnt = 0
                req_dict[key.upper()] = cnt
                req_original[key.upper()] = key
    
    raid_obj.required_sps = req_dict
    raid_obj.required_sps_original = req_original
    bot.raids[channel_id] = raid_obj
    save_raid_to_db(raid_obj)
    
    # Use ephemeral message for confirmation
    await ephemeral_response(interaction,
                         (f"Raid **{raid_name}** created on {parsed_dt.strftime('%Y-%m-%d %H:%M %Z')}.\n"
                          f"Description: {description}\n"
                          f"Max={max_players}, Alts={allow_alts}, max_alts={max_alts}.\n"
                          f"Priority={priority}, prioritylist='{prioritylist}', hours={priority_hours}.\n"
                          f"Required SPs={req_dict}."))
    
    # Send raid message to channel
    channel = interaction.channel
    msg = await channel.send(content=raid_obj.format_raid_list(), view=RaidManagementView(raid_obj))
    raid_obj.raid_message = msg
    raid_obj._stored_message_id = msg.id
    
    # Mention users on creation
    await raid_obj.mention_on_creation()

@app_commands.command(name="raids_list", description="List all active raids.")
async def raids_list_slash(interaction: discord.Interaction):
    """List all active raids."""
    bot = interaction.client
    
    if not bot.raids:
        # Use ephemeral message
        await ephemeral_response(interaction, "No active raids.")
        return
    
    lines = []
    for r in bot.raids.values():
        lines.append(
            f"<#{r.channel_id}>: {r.raid_name}, {r.count_main_alt()}/{r.max_players} slots filled, "
            f"Priority={r.priority}, prioritylist='{r.prioritylist_str}', reqSP={r.required_sps}"
        )
    
    # Use ephemeral message
    await ephemeral_response(interaction, "\n".join(lines))

@app_commands.command(name="raid_template", description="Use a raid template to assign roles.")
async def raid_template_slash(interaction: discord.Interaction):
    """Use a raid template to assign roles."""
    bot = interaction.client
    channel_id = interaction.channel_id
    
    if channel_id not in bot.raids:
        # Use ephemeral message
        await ephemeral_response(interaction, "No active raid in this channel.")
        return
    
    raid_obj = bot.raids[channel_id]
    if interaction.user != raid_obj.creator:
        # Use ephemeral message
        await ephemeral_response(interaction, "Only the raid creator can use raid templates.")
        return
    
    from utils import load_templates
    templates = load_templates()
    if not templates:
        # Use ephemeral message
        await ephemeral_response(interaction, "No templates available.")
        return
    
    # Use ephemeral message with view
    await ephemeral_response(interaction, "Select a raid template:", 
                         view=RaidTemplateSelectView(raid_obj, templates),
                         wait_for_user_action=True)