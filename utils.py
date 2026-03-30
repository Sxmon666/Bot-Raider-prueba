import json
import asyncio
from typing import Optional, Dict

import discord
from discord.ui import View

# =====================================================
# Load Templates Function
# =====================================================
def load_templates() -> Dict[str, dict]:
    try:
        with open("raid_templates.json", "r", encoding="utf-8") as f:
            templates = json.load(f)
        return templates
    except Exception as e:
        print(f"Error loading raid templates: {e}")
        return {}

# =====================================================
# Helper Functions
# =====================================================
async def safe_edit_message(message: discord.Message, **kwargs):
    if message.author.id != message._state.user.id:
        print("Cannot edit message not authored by the bot.")
        return
    if "content" in kwargs and len(kwargs["content"]) > 1900:
        kwargs["content"] = kwargs["content"][:1900] + "\n...[truncated]"
    await message.edit(**kwargs)

async def ephemeral_response(interaction: discord.Interaction, content: str, view: Optional[View] = None,
                         wait_for_user_action: bool = False):
    try:
        if not interaction.response.is_done():
            await interaction.response.send_message(content, ephemeral=True, view=view)
        else:
            await interaction.followup.send(content, ephemeral=True, view=view)
    except Exception as e:
        print("ephemeral_response error:", e)
    if not wait_for_user_action:
        await asyncio.sleep(5)
        try:
            await interaction.delete_original_response()
        except discord.HTTPException as e:
            if e.code != 10015:
                print(f"Error deleting ephemeral message: {e}")