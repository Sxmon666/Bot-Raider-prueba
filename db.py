import os
import json
import redis
from typing import Optional

# =====================================================
# Redis Setup
# =====================================================
REDIS_URL = os.getenv("REDISCLOUD_URL", "redis://localhost:6379")
redis_client = redis.StrictRedis.from_url(REDIS_URL, decode_responses=True)

def ensure_db_table():
    pass

def save_raid_to_db(raid):
    key = f"raid:{raid.guild.id}:{raid.channel_id}"
    data_json = json.dumps(raid.to_dict())
    redis_client.set(key, data_json)

def load_all_raids_from_db(bot):
    keys = redis_client.keys("raid:*")
    for key in keys:
        data_json = redis_client.get(key)
        if not data_json:
            continue
        data = json.loads(data_json)
        if key.count(":") < 2:
            parts = key.split(":")
            if len(parts) == 2:
                try:
                    channel_id = int(parts[1])
                except ValueError:
                    continue
                channel = bot.get_channel(channel_id)
                if channel and channel.guild:
                    guild_id = channel.guild.id
                    data["guild_id"] = guild_id
                    new_key = f"raid:{guild_id}:{channel_id}"
                    redis_client.set(new_key, json.dumps(data))
                    redis_client.delete(key)
                    key = new_key
        raid = bot.raid_class.from_dict(data, bot)
        if raid is not None:
            bot.raids[int(raid.channel_id)] = raid

def remove_raid_from_db(channel_id: int, guild_id: int):
    key = f"raid:{guild_id}:{channel_id}"
    redis_client.delete(key)