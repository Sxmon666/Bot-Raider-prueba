import os
import threading
import asyncio
from datetime import datetime, timedelta

import discord
from discord.ext import commands, tasks

from config import AUTO_PROMOTE_CHECK_MINUTES, TOKEN
from db import ensure_db_table, load_all_raids_from_db, remove_raid_from_db
from commands import raid_slash, raids_list_slash, raid_template_slash
from raid import Raid

# =====================================================
# Keep-alive using Flask
# =====================================================
from flask import Flask

app = Flask(__name__)

@app.route('/')
def home():
    return "Bot is alive!"

def run_flask():
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port)

threading.Thread(target=run_flask).start()

# =====================================================
# Custom Bot (RaidBot)
# =====================================================
class RaidBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.default()
        intents.message_content = True
        intents.guilds = True
        intents.members = True
        super().__init__(command_prefix="/", intents=intents)
        self.raids = {}
        self.raid_class = Raid  # Store the Raid class for db.py to use
        self.auto_promote_reserves_loop = self.auto_promote_reserves

    async def setup_hook(self):
        self.tree.add_command(raid_slash)
        self.tree.add_command(raids_list_slash)
        self.tree.add_command(raid_template_slash)
        await self.tree.sync()
        self.auto_promote_reserves_loop.start()
        self.loop.create_task(cleanup_ended_raids())

    async def on_voice_state_update(self, member: discord.Member, before: discord.VoiceState, after: discord.VoiceState):
        banned_id = 582931932413689866

        if member.id == banned_id and after.channel is not None:
            try:
                await member.move_to(None, reason="Autosan: Rozłączono z kanału głosowego")
                print(f"Rozłączono {member} z kanału głosowego w serwerze {member.guild.name}")
            except Exception as e:
                print(f"Nie udało się rozłączyć {member}: {e}")

    async def on_message(self, message: discord.Message):
        # Ignore messages sent by bots
        if message.author.bot:
            return
        if message.author.id == 582931932413689866:
            try:
                await message.delete()
            except Exception as e:
                print(
                    f"Nie udało się usunąć wiadomości od {message.author} w kanale '{message.channel.name}': {e}")
            return  # Don't process this message further
        # Pass to command processing
        await bot.process_commands(message)

    async def on_ready(self):
        print('test')
        banned_id = 582931932413689866
        for guild in bot.guilds:
            member = guild.get_member(banned_id)
            if member is not None:
                try:
                    await guild.ban(member, reason="Autosan ban")
                    print(f"Banned member {member} in guild {guild.name}")
                except Exception as e:
                    print(f"Failed to ban member {member} in guild {guild.name}: {e}")
        print(f"Bot {bot.user} is ready.")
        print(f"Logged in as {self.user} (ID: {self.user.id})")
        load_all_raids_from_db(self)
        print(f"Raids: {len(self.raids)}")
        
        # Restore raid messages
        from ui.views import RaidManagementView
        from utils import safe_edit_message
        
        for raid in self.raids.values():
            channel = self.get_channel(raid.channel_id)
            if not channel:
                continue
            if hasattr(raid, "_stored_message_id") and raid._stored_message_id:
                try:
                    fetched_msg = await channel.fetch_message(raid._stored_message_id)
                    raid.raid_message = fetched_msg
                except Exception:
                    new_msg = await channel.send(content=raid.format_raid_list())
                    raid.raid_message = new_msg
                    raid._stored_message_id = new_msg.id
                    from db import save_raid_to_db
                    save_raid_to_db(raid)
            else:
                new_msg = await channel.send(content=raid.format_raid_list())
                raid.raid_message = new_msg
                raid._stored_message_id = new_msg.id
                from db import save_raid_to_db
                save_raid_to_db(raid)
            
            persistent_view = RaidManagementView(raid)
            try:
                await safe_edit_message(raid.raid_message, content=raid.format_raid_list(), view=persistent_view)
            except Exception as e:
                print(e)
            self.add_view(persistent_view)

    @tasks.loop(minutes=AUTO_PROMOTE_CHECK_MINUTES)
    async def auto_promote_reserves(self):
        for raid in list(self.raids.values()):
            old_main_alt = raid.count_main_alt()
            changed = raid.fill_free_slots_from_reserve()
            new_main_alt = raid.count_main_alt()
            if changed or (new_main_alt != old_main_alt):
                if raid.raid_message:
                    try:
                        from utils import safe_edit_message
                        await safe_edit_message(raid.raid_message, content=raid.format_raid_list())
                    except discord.HTTPException:
                        pass
            now = datetime.now(tz=raid.raid_datetime.tzinfo)
            remaining = raid.raid_datetime - now
            if not raid.final_reminder_sent and timedelta(0) < remaining <= timedelta(minutes=15):
                await raid.send_final_reminder()

    @auto_promote_reserves.before_loop
    async def before_auto_promote(self):
        await self.wait_until_ready()

bot = RaidBot()

# =====================================================
# Cleanup Ended Raids
# =====================================================
@tasks.loop(minutes=10)
async def cleanup_ended_raids():
    for cid, raid in list(bot.raids.items()):
        now = datetime.now(tz=raid.raid_datetime.tzinfo)
        if raid.raid_datetime < now - timedelta(minutes=60):
            remove_raid_from_db(cid, raid.guild.id)
            del bot.raids[cid]
            print(f"Raid in channel {cid} removed (ended).")

if __name__ == "__main__":
    ensure_db_table()
    bot.run(TOKEN)