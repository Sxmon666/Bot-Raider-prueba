import discord
from discord.ui import Button

class CloseButton(Button):
    """Button to close a view."""
    
    def __init__(self):
        super().__init__(label="X", style=discord.ButtonStyle.danger, custom_id="close_button")
    
    async def callback(self, interaction: discord.Interaction):
        try:
            await interaction.response.edit_message(delete_after=1)
        except Exception:
            try:
                await interaction.message.delete()
            except Exception as e:
                print(f"Error closing view: {e}")
        self.view.stop()

class NotifyParticipantsButton(Button):
    """Button to notify raid participants."""
    
    def __init__(self):
        super().__init__(style=discord.ButtonStyle.primary, label="Notify Participants")
    
    async def callback(self, interaction: discord.Interaction):
        """Handle button click."""
        # Get the raid
        raid = self.view.raid
        if interaction.user != raid.creator:
            # Use ephemeral message
            await interaction.response.send_message("Only the raid leader can notify participants.", ephemeral=True)
            return
        
        if raid.notify_sent:
            # Use ephemeral message
            await interaction.response.send_message("Notification already sent.", ephemeral=True)
            return
        
        # Check time constraints
        import discord.utils
        from config import NOTIFY_THRESHOLD
        
        now = discord.utils.utcnow()
        if now >= raid.raid_datetime:
            # Use ephemeral message
            await interaction.response.send_message("The raid has already started; notification cannot be sent.", ephemeral=True)
            self.disabled = True
            try:
                await interaction.response.edit_message(view=self.view)
            except discord.errors.InteractionResponded:
                pass
            return
        
        if raid.raid_datetime - now > NOTIFY_THRESHOLD:
            # Use ephemeral message
            await interaction.response.send_message("Too early to notify participants (more than 1 hour remaining).", ephemeral=True)
            return
        
        # Send notifications
        await raid.notify_participants()
        raid.notify_sent = True
        
        # Import save_raid_to_db here to avoid circular imports
        from db import save_raid_to_db
        save_raid_to_db(raid)
        
        # Use ephemeral message for confirmation
        await interaction.response.send_message("Participants notified via DM.", ephemeral=True)

class SendListButton(Button):
    """Button to send a template list."""
    
    def __init__(self, organizer):
        super().__init__(label="Send List", style=discord.ButtonStyle.success, custom_id="send_list")
        self.organizer = organizer
    
    async def callback(self, interaction: discord.Interaction):
        if not self.organizer.assignments:
            # Use ephemeral message
            await interaction.response.send_message("No assignments made.", ephemeral=True, view=self.organizer)
            return
        
        content = f"Template **{self.organizer.template_name}** final assignments:\n"
        for role, data in self.organizer.assignments.items():
            if data["id"]:
                mention = f"<@{data['id']}>"
            else:
                mention = data["display"]
            content += f"**{role}**: {mention}\n"
        
        # Send direct messages to participants (ephemeral-like)
        for p in self.organizer.raid.participants:
            member = self.organizer.raid.guild.get_member(p.user_id)
            if member:
                try:
                    await member.send(content)
                except Exception as e:
                    print(f"Error sending DM to {member}: {e}")
        
        # Also send to channel for reference
        channel = self.organizer.raid.bot.get_channel(self.organizer.raid.channel_id)
        if channel:
            await channel.send(content)
        
        # Use ephemeral message for confirmation
        await interaction.response.send_message("Final assignments sent.", ephemeral=True)