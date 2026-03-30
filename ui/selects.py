import discord
from discord.ui import Select
from typing import List, Optional

class ClassDropdown(Select):
    """Dropdown for selecting a class."""
    
    def __init__(self, raid, participant_type: str):
        from config import specializations
        
        self.raid = raid
        self.participant_type = participant_type
        opts = [discord.SelectOption(label=c, value=c) for c in specializations]
        super().__init__(placeholder="Select a class", options=opts)
    
    async def callback(self, interaction: discord.Interaction):
        """Handle selection."""
        chosen_class = self.values[0]
        
        # Import here to avoid circular imports
        from ui.views import SPSelectionView
        
        # Use ephemeral message
        await interaction.response.edit_message(
            content=f"Selected class: **{chosen_class}**. Now pick an SP:",
            view=SPSelectionView(self.raid, chosen_class, self.participant_type)
        )

class SPDropdown(Select):
    """Dropdown for selecting a specialization."""
    
    def __init__(self, raid, chosen_class: str, chosen_sps: List[str]):
        from config import specializations
        
        all_sps = specializations[chosen_class]
        opts = []
        for sp in all_sps:
            if sp not in chosen_sps:
                emoji_name = sp.strip(":")
                emoji_val = raid.emoji_map.get(emoji_name) if hasattr(raid, "emoji_map") else None
                label_text = sp.split("_")[-1].strip(":") if "_" in sp else sp.strip(":")
                opts.append(discord.SelectOption(label=label_text, value=sp, emoji=emoji_val))
        super().__init__(placeholder="Pick an SP", options=opts)
        self.raid = raid
        self.chosen_class = chosen_class
        self.chosen_sps = chosen_sps
    
    async def callback(self, interaction: discord.Interaction):
        """Handle selection."""
        sp = self.values[0]
        if sp not in self.chosen_sps:
            self.chosen_sps.append(sp)
        
        # Use ephemeral message
        await interaction.response.edit_message(
            content=f"Chosen SP(s): {', '.join(self.chosen_sps)}. Click 'Sign Up' or add more.",
            view=self.view
        )

class RoleSelectMenu(Select):
    """Menu for selecting a role in a template organizer."""
    
    def __init__(self, role_name: str, options: List[discord.SelectOption], organizer):
        self.role_name = role_name
        self.organizer = organizer
        super().__init__(placeholder=f"Select user for {role_name}", options=options, min_values=1, max_values=1)
    
    async def callback(self, interaction: discord.Interaction):
        """Handle selection."""
        selected = self.values[0]
        if selected == "-1":
            self.organizer.assignments[self.role_name] = {"display": "No participant", "id": None}
        else:
            member = self.organizer.raid.guild.get_member(int(selected))
            if member:
                self.organizer.assignments[self.role_name] = {"display": member.display_name, "id": member.id}
            else:
                self.organizer.assignments[self.role_name] = {"display": f"User-{selected}", "id": None}
        
        # Use ephemeral message
        await interaction.response.edit_message(content=self.organizer.get_preview(), view=self.organizer)

class RaidTemplateSelectDropdown(Select):
    """Dropdown for selecting a raid template."""
    
    def __init__(self, options: List[discord.SelectOption]):
        super().__init__(placeholder="Select a raid template", options=options, min_values=1, max_values=1)
    
    async def callback(self, interaction: discord.Interaction):
        """Handle selection."""
        from utils import load_templates
        
        template_name = self.values[0]
        templates = load_templates()
        template_data = templates.get(template_name)
        if not template_data:
            # Use ephemeral message
            await interaction.response.send_message("Selected template not found.", ephemeral=True)
            return
        
        raid = self.view.raid
        if interaction.user != raid.creator:
            # Use ephemeral message
            await interaction.response.send_message("Only the raid creator can use templates.", ephemeral=True)
            return
        
        # Import here to avoid circular imports
        from ui.views import TemplateOrganizerView
        
        # Use ephemeral message
        await interaction.response.edit_message(
            content=f"Organize template **{template_name}**",
            view=TemplateOrganizerView(raid, template_name, template_data)
        )

class PromoteReserveDropdown(Select):
    """Dropdown for promoting a user from reserve."""
    
    def __init__(self, raid):
        self.raid = raid
        reserves = [p for p in raid.participants if p.participant_type == "RESERVE"]
        if not reserves:
            opts = [discord.SelectOption(label="No one in reserve", value="-1")]
        else:
            opts = []
            for p in reserves:
                mem = raid.guild.get_member(p.user_id)
                disp = mem.display_name if mem else f"User-{p.user_id}"
                opts.append(discord.SelectOption(label=f"{disp} ({p.reserve_for}) {p.sp}", value=str(p.user_id)))
        super().__init__(placeholder="Choose user to promote", options=opts)
    
    async def callback(self, interaction: discord.Interaction):
        """Handle selection."""
        from utils import ephemeral_response, safe_edit_message
        
        val = self.values[0]
        if val == "-1":
            # Use ephemeral message
            await ephemeral_response(interaction, "No one is on reserve!")
            return
        
        uid = int(val)
        promoted_user = self.raid.force_promote_reserve_user(uid)
        if promoted_user and self.raid.raid_message:
            await safe_edit_message(self.raid.raid_message, content=self.raid.format_raid_list())
            channel = self.raid.bot.get_channel(self.raid.channel_id)
            if channel:
                # Send direct message to promoted user (ephemeral-like)
                member = self.raid.guild.get_member(promoted_user)
                if member:
                    try:
                        await member.send(f"You have been promoted from reserve in raid **{self.raid.raid_name}**!")
                    except Exception as e:
                        print(f"Error sending promotion DM to {member}: {e}")
                
                # Also send to channel for reference
                await channel.send(f"<@{promoted_user}> has been promoted from reserve!")
        
        msg = f"Promoted <@{promoted_user}> from reserve!" if promoted_user else "Could not promote user."
        # Use ephemeral message
        await ephemeral_response(interaction, msg)

class RequiredSPDropdown(Select):
    """Dropdown for selecting a required SP."""
    
    def __init__(self, raid):
        self.raid = raid
        unfilled = raid.get_unfilled_required_sps()
        if unfilled:
            opts = [discord.SelectOption(label=x, value=x.upper()) for x in unfilled]
        else:
            opts = [discord.SelectOption(label="All required SPs fulfilled", value="-1")]
        super().__init__(placeholder="Pick Required SP to fill", options=opts)
    
    async def callback(self, interaction: discord.Interaction):
        """Handle selection."""
        from utils import ephemeral_response, safe_edit_message
        
        val = self.values[0]
        if val == "-1":
            # Use ephemeral message
            await ephemeral_response(interaction, "No required SPs left")
            return
        
        user = interaction.user
        sp_choice = val
        ok = self.raid.add_participant(user, sp_choice, "MAIN", ignore_required=False)
        if ok and self.raid.raid_message:
            await safe_edit_message(self.raid.raid_message, content=self.raid.format_raid_list())
            # Use ephemeral message
            await ephemeral_response(interaction, f"You signed up with required SP: {self.raid.required_sps_original.get(val, val)}!")
        else:
            # Use ephemeral message
            await ephemeral_response(interaction, "Could not sign up with that SP.")


class SlotOrderSelect(Select):
    def __init__(self, idx, player_list, guild, current_player_id=None):
        options = []
        # Dodaj "pustą" opcję (żeby można było zostawić slot pusty)
        options.append(discord.SelectOption(label="(puste)", value="-1", default=(current_player_id is None)))
        self.idx = idx
        self.guild = guild
        self.row = idx // 5
        for p in player_list:
            member = guild.get_member(p.user_id)
            display_name = member.display_name if member else f"ID {p.user_id}"
            options.append(discord.SelectOption(
                label=display_name,
                value=str(p.user_id),
                default=(str(p.user_id) == str(current_player_id))
            ))
        super().__init__(
            placeholder=f"Wybierz gracza na miejsce {idx+1}",
            min_values=1,
            max_values=1,
            options=options,
            custom_id=f"slotorder_{idx}",

        )


    async def callback(self, interaction):
        selected_id = self.values[0]
        if selected_id == "-1":
            self.view.assignments[self.idx] = {
                "id": None,
                "display": "(puste)"
            }
        else:
            member = self.guild.get_member(int(selected_id))
            display = member.display_name if member else f"ID {selected_id}"
            self.view.assignments[self.idx] = {
                "id": int(selected_id),
                "display": display
            }
        await interaction.response.edit_message(
            content=self.view.get_preview(),
            view=self.view
        )