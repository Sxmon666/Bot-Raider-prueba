from logging import log
import re
import json
import asyncio
from datetime import datetime, timedelta
from typing import Optional, List, Dict
from zoneinfo import ZoneInfo

import discord
from discord.ext import commands

from config import ROLE_MARATO, ROLE_CZLONEK, ROLE_MLODY_CZLONEK, ROLE_ALT_ALLOW, STANDARD_MENTION_ROLES,ROLE_REZERWA
from utils import safe_edit_message
from db import save_raid_to_db

# =====================================================
# Participant Class
# =====================================================
class Participant:
    def __init__(self, user_id: int, sp: str, participant_type: str,
                 reserve_for: Optional[str] = None, is_required_sp: bool = False, level_offset: int = 0,
                 required_sp_list: Optional[List[str]] = None):
        self.user_id = user_id
        self.sp = sp
        self.participant_type = participant_type
        self.reserve_for = reserve_for
        self.is_required_sp = is_required_sp
        self.level_offset = level_offset
        self.required_sp_list = required_sp_list if required_sp_list is not None else []

# =====================================================
# Raid Class
# =====================================================
class Raid:
    def __init__(self, channel_id: int, creator: discord.Member, raid_name: str,
                 raid_datetime: datetime, max_players: int, allow_alts: bool,
                 max_alts: int, priority: bool, prioritylist: str, priority_hours: int,
                 bot: commands.Bot, description: str = ""):
        self.channel_id = channel_id
        self.creator = creator
        self.guild = creator.guild
        self.guild_id = creator.guild.id
        self.raid_name = raid_name
        self.description = description
        self.raid_datetime = raid_datetime
        self.max_players = max_players
        self.allow_alts = allow_alts
        self.max_alts = max_alts
        self.priority = priority
        self.prioritylist_str = prioritylist
        self.priority_hours = priority_hours
        self.priority_roles: List[int] = []
        if self.priority and prioritylist.strip():
            for nm in prioritylist.split(","):
                nm = nm.strip()
                if nm:
                    role_obj = discord.utils.find(lambda r: r.name.lower() == nm.lower(), self.guild.roles)
                    if role_obj:
                        self.priority_roles.append(role_obj.id)
        self.bot = bot
        self.participants: List[Participant] = []
        self.raid_message: Optional[discord.Message] = None
        self.tracked_messages: List[int] = []
        self.required_sps: Dict[str, int] = {}
        self.emoji_map = {e.name: str(e) for e in self.guild.emojis} if self.guild else {}
        self.required_sps_original: Dict[str, str] = {}
        self._stored_message_id: Optional[int] = None
        self.final_reminder_sent = False
        self.notify_sent = False

    def to_dict(self) -> dict:
        return {
            "guild_id": self.guild.id,
            "channel_id": self.channel_id,
            "creator_id": self.creator.id,
            "raid_name": self.raid_name,
            "description": self.description,
            "raid_datetime": self.raid_datetime.isoformat(),
            "max_players": self.max_players,
            "allow_alts": self.allow_alts,
            "max_alts": self.max_alts,
            "priority": self.priority,
            "prioritylist_str": self.prioritylist_str,
            "priority_hours": self.priority_hours,
            "participants": [vars(p) for p in self.participants],
            "required_sps": self.required_sps,
            "required_sps_original": self.required_sps_original,
            "raid_message_id": self.raid_message.id if self.raid_message else self._stored_message_id,
            "final_reminder_sent": self.final_reminder_sent,
            "notify_sent": self.notify_sent
        }

    @classmethod
    def from_dict(cls, data: dict, bot: commands.Bot) -> Optional["Raid"]:
        if "participants" in data:
            for p in data["participants"]:
                if "required_sp_list" not in p:
                    p["required_sp_list"] = []
        guild = bot.get_guild(data["guild_id"])
        if guild is None:
            return None
        creator = guild.get_member(data["creator_id"])
        if creator is None:
            return None
        raid_datetime = datetime.fromisoformat(data["raid_datetime"])
        if raid_datetime.tzinfo is None:
            raid_datetime = raid_datetime.replace(tzinfo=ZoneInfo("Europe/Warsaw"))
        description = data.get("description", "")
        raid = cls(
            channel_id=data["channel_id"],
            creator=creator,
            raid_name=data["raid_name"],
            description=description,
            raid_datetime=raid_datetime,
            max_players=data["max_players"],
            allow_alts=data["allow_alts"],
            max_alts=data["max_alts"],
            priority=data["priority"],
            prioritylist=data["prioritylist_str"],
            priority_hours=data["priority_hours"],
            bot=bot
        )
        raid.participants = [Participant(**p_data) for p_data in data["participants"]]
        raid.required_sps = data["required_sps"]
        raid.required_sps_original = data.get("required_sps_original", {})
        raid._stored_message_id = data.get("raid_message_id")
        raid.final_reminder_sent = data.get("final_reminder_sent", False)
        raid.notify_sent = data.get("notify_sent", False)
        return raid

    async def track_bot_message(self, msg: discord.Message):
        self.tracked_messages.append(msg.id)
        save_raid_to_db(self)

    async def delete_all_tracked_messages(self):
        channel = self.bot.get_channel(self.channel_id)
        if channel:
            for mid in self.tracked_messages:
                try:
                    m = await channel.fetch_message(mid)
                    await m.delete()
                except:
                    pass
        self.tracked_messages.clear()

    def _has_role_by_name(self, user_id: int, role_name: str) -> bool:
        member = self.guild.get_member(user_id)
        return member is not None and any(r.name.lower() == role_name.lower() for r in member.roles)

    def _has_role_id(self, user_id: int, role_id: int) -> bool:
        member = self.guild.get_member(user_id)
        return member is not None and any(r.id == role_id for r in member.roles)

    def is_marato(self, user_id: int) -> bool:
        return self._has_role_by_name(user_id, ROLE_MARATO)

    def is_in_priority(self, user_id: int, role_list: List[int]) -> bool:
        member = self.guild.get_member(user_id)
        return member is not None and any(r.id in role_list for r in member.roles)

    def is_czlonek(self, user_id: int) -> bool:
        return self._has_role_by_name(user_id, ROLE_CZLONEK)

    def is_mlody_czlonek(self, user_id: int) -> bool:
        return self._has_role_by_name(user_id, ROLE_MLODY_CZLONEK)

    def has_alt_role(self, user_id: int) -> bool:
        return self._has_role_by_name(user_id, ROLE_ALT_ALLOW)

    def has_rezerwa_role(self, user_id: int) -> bool:
        return self._has_role_by_name(user_id, ROLE_REZERWA)

    def user_in_priority_roles(self, user_id: int) -> bool:
        for rid in self.priority_roles:
            if self._has_role_id(user_id, rid):
                return True
        return False

    def count_main_alt(self) -> int:
        return sum(1 for p in self.participants if p.participant_type in ("MAIN", "ALT"))

    def is_full(self) -> bool:
        return self.count_main_alt() >= self.max_players

    def has_real_main(self, user_id: int) -> bool:
        return any(p for p in self.participants if p.user_id == user_id and p.participant_type == "MAIN")

    def has_main_or_reserve_for_main(self, user_id: int) -> bool:
        return any(p for p in self.participants if p.user_id == user_id and (
            p.participant_type == "MAIN" or (p.participant_type == "RESERVE" and p.reserve_for == "MAIN")
        ))

    def count_alts_for_user(self, user_id: int) -> int:
        return sum(1 for p in self.participants if p.user_id == user_id and (
            p.participant_type == "ALT" or (p.participant_type == "RESERVE" and p.reserve_for == "ALT")
        ))

    def count_reserve(self) -> int:
        return sum(1 for p in self.participants if p.participant_type == "RESERVE")

    def get_unfilled_required_sps(self) -> List[str]:
        result = []
        for canon, cnt in self.required_sps.items():
            if cnt > 0:
                orig = self.required_sps_original.get(canon, canon)
                result.append(orig)
        return result

    def any_required_sp_needed(self) -> bool:
        return any(v > 0 for v in self.required_sps.values())

    def decrement_required_sp(self, sp_name: str):
        canon = sp_name.upper()
        if canon in self.required_sps and self.required_sps[canon] > 0:
            self.required_sps[canon] -= 1
            save_raid_to_db(self)

    def increment_required_sp(self, sp_name: str):
        canon = sp_name.upper()
        if canon in self.required_sps:
            self.required_sps[canon] += 1
            save_raid_to_db(self)

    def add_participant(self, user: discord.Member, sp: str, desired_type: str,
                        ignore_required: bool = True, level_offset: int = 0) -> bool:
        user_id = user.id
        now = datetime.now(tz=self.raid_datetime.tzinfo)
        time_left = self.raid_datetime - now

        # During priority period, force non-priority into reserve—applies to both MAIN and ALT
        forced_reserve_for_priority = False
        if self.priority and time_left > timedelta(hours=self.priority_hours):
            if not self.is_in_priority(user_id, self.priority_roles):
                forced_reserve_for_priority = True

        if self.has_rezerwa_role(user_id):
            print(self.has_rezerwa_role(user_id))
            forced_reserve_for_priority = True

        # Normalize SP strings
        sp_items_original = [s.strip() for s in sp.split(",") if s.strip()]
        sp_list = [s.strip(":").upper() for s in sp_items_original]

        # ALT-specific checks (no required SPs, alts allowed, etc.)
        if desired_type.upper() == "ALT":
            for sp_item in sp_list:
                if sp_item in self.required_sps and self.required_sps[sp_item] > 0:
                    return False
            if not self.allow_alts or not self.has_main_or_reserve_for_main(user_id):
                return False
            if self.count_alts_for_user(user_id) >= self.max_alts:
                return False

        # Required-SP logic (only MAINs can fill required)
        required_found = [sp_item for sp_item in sp_list
                          if sp_item in self.required_sps and self.required_sps[sp_item] > 0]
        if required_found:
            if desired_type.upper() != "MAIN" or ignore_required:
                return False
        is_req_sp = bool(required_found)
        sp_str = ", ".join(sp_items_original)

        # Build the Participant object
        if forced_reserve_for_priority:
            # Non-priority during priority window -> always RESERVE
            reserve_for = desired_type.upper()
            part = Participant(user_id, sp_str, "RESERVE", reserve_for, is_req_sp, level_offset)
        else:
            # Normal flow
            if desired_type.upper() == "MAIN":
                if self.has_real_main(user_id):
                    return False
                if self.is_full():
                    part = Participant(user_id, sp_str, "RESERVE", "MAIN", is_req_sp, level_offset)
                else:
                    part = Participant(user_id, sp_str, "MAIN", None, is_req_sp, level_offset)

            elif desired_type.upper() == "ALT":
                part = Participant(user_id, sp_str, "ALT", None, is_req_sp, level_offset)

            else:
                part = Participant(user_id, sp_str, "RESERVE", "MAIN", is_req_sp, level_offset)

        # Commit
        self.participants.append(part)
        for sp_item in required_found:
            self.decrement_required_sp(sp_item)
        self.fill_free_slots_from_reserve()
        save_raid_to_db(self)
        return True

    async def send_promotion_notification(self, user_id: int):
        member = self.guild.get_member(user_id)
        if member:
            try:
                # Send direct message (ephemeral-like)
                await member.send(f"You have been promoted from reserve to main in raid **{self.raid_name}**!")
            except Exception as e:
                print(f"Error sending promotion notification to {member}: {e}")

    def fill_free_slots_from_reserve(self) -> bool:
        changed = False
        free_slots = self.max_players - self.count_main_alt()
        if free_slots <= 0:
            return changed
        tz = self.raid_datetime.tzinfo or ZoneInfo("Europe/Warsaw")
        now = datetime.now(tz=tz)
        time_left = self.raid_datetime - now

        def can_promote(uid: int) -> bool:
            if self.priority and time_left > timedelta(hours=self.priority_hours):
                return self.is_in_priority(uid, self.priority_roles)
            if self.has_rezerwa_role(uid):
                return False
            return True

        while free_slots > 0:
            promoted_anyone = False
            for p in self.participants:
                if p.participant_type != "RESERVE":
                    continue
                if self.count_main_alt() >= self.max_players:
                    break
                if not can_promote(p.user_id):
                    continue
                if p.reserve_for == "ALT":
                    if not self.allow_alts:
                        continue
                    if not self.has_alt_role(p.user_id):
                        continue
                    if not self.has_main_or_reserve_for_main(p.user_id):
                        continue
                    if self.count_alts_for_user(p.user_id) >= self.max_alts:
                        continue
                    p.participant_type = "ALT"
                    p.reserve_for = None
                    free_slots -= 1
                    changed = True
                    promoted_anyone = True
                    asyncio.create_task(self.send_promotion_notification(p.user_id))
                else:
                    if self.has_real_main(p.user_id):
                        continue
                    p.participant_type = "MAIN"
                    p.reserve_for = None
                    free_slots -= 1
                    changed = True
                    promoted_anyone = True
                    asyncio.create_task(self.send_promotion_notification(p.user_id))
                if free_slots <= 0:
                    break
            if not promoted_anyone:
                break
        if changed:
            save_raid_to_db(self)
        return changed

    def force_promote_next_reserve(self) -> Optional[int]:
        for p in self.participants:
            if p.participant_type == "RESERVE":
                if self.count_main_alt() >= self.max_players:
                    return None
                user_id = p.user_id
                if p.reserve_for == "ALT":
                    if not self.allow_alts:
                        return None
                    if not self.has_alt_role(user_id):
                        return None
                    if not self.has_main_or_reserve_for_main(user_id):
                        return None
                    if self.count_alts_for_user(user_id) >= self.max_alts:
                        return None
                    p.participant_type = "ALT"
                    p.reserve_for = None
                    save_raid_to_db(self)
                    return user_id
                else:
                    if self.has_real_main(user_id):
                        continue
                    p.participant_type = "MAIN"
                    p.reserve_for = None
                    save_raid_to_db(self)
                    return user_id
        return None

    def force_promote_reserve_user(self, user_id: int) -> Optional[int]:
        if self.count_main_alt() >= self.max_players:
            return None
        for p in self.participants:
            if p.user_id == user_id and p.participant_type == "RESERVE":
                if p.reserve_for == "ALT":
                    if not self.allow_alts:
                        return None
                    if not self.has_alt_role(user_id):
                        return None
                    if not self.has_main_or_reserve_for_main(user_id):
                        return None
                    if self.count_alts_for_user(user_id) >= self.max_alts:
                        return None
                    p.participant_type = "ALT"
                    p.reserve_for = None
                    save_raid_to_db(self)
                    return user_id
                else:
                    if self.has_real_main(user_id):
                        return None
                    p.participant_type = "MAIN"
                    p.reserve_for = None
                    save_raid_to_db(self)
                    return user_id
        return None

    async def remove_participant(self, user_id: int, remover: discord.Member = None) -> bool:
        before = len(self.participants)
        removed_entries = [p for p in self.participants if p.user_id == user_id]
        self.participants = [p for p in self.participants if p.user_id != user_id]
        removed_any = (len(self.participants) < before)
        if removed_any:
            for p in removed_entries:
                if p.is_required_sp:
                    # Normalize SP entries when returning values
                    for sp_item in [s.strip(":").upper() for s in p.sp.split(",")]:
                        if sp_item in self.required_sps:
                            self.increment_required_sp(sp_item)
            self.fill_free_slots_from_reserve()
            if self.raid_message:
                try:
                    await safe_edit_message(self.raid_message, content=self.format_raid_list())
                except discord.HTTPException:
                    pass
            channel = self.bot.get_channel(self.channel_id)
            if channel:
                if self.priority:
                    mention_list = []
                    for rid in self.priority_roles:
                        r_obj = self.guild.get_role(rid)
                        if r_obj:
                            mention_list.append(r_obj.mention)
                    mention_block = " ".join(mention_list)
                else:
                    mention_list = []
                    for role_name in STANDARD_MENTION_ROLES:
                        r_obj = discord.utils.get(self.guild.roles, name=role_name)
                        if r_obj:
                            mention_list.append(r_obj.mention)
                    mention_block = " ".join(mention_list)

                # Send direct message to the user (ephemeral-like)
                member = self.guild.get_member(user_id)
                if member:
                    try:
                        await member.send(f"You have been removed from raid **{self.raid_name}**.")
                    except Exception as e:
                        print(f"Error sending removal notification to {member}: {e}")

                # Also send to channel for reference
                user_disp = f"<@{user_id}>"
                remover_info = f" by {remover.mention}" if remover else ""
                await channel.send(f"{self.creator.mention} – {user_disp} has left the raid!")

                prio_info = ''
                if self.priority and self.count_reserve() == 0:
                    now = datetime.now(tz=self.raid_datetime.tzinfo)
                    time_left = self.raid_datetime - now
                    if time_left > timedelta(hours=self.priority_hours):
                        prio_remaining = time_left - timedelta(hours=self.priority_hours)
                        hours, remainder = divmod(int(prio_remaining.total_seconds()), 3600)
                        minutes = remainder // 60
                        prio_info = f"Priority active for another {hours}h {minutes}m."
                    else:
                        prio_info = "Priority period has ended."

                raid_info = f"{user_disp} was removed from the raid{remover_info}."
                msg = await channel.send(f"{raid_info} {prio_info}")
                await self.track_bot_message(msg)

                from config import WARN_THRESHOLD_MINUTES
                now = datetime.now(tz=self.raid_datetime.tzinfo)
                remaining = self.raid_datetime - now
                if remaining > timedelta(0) and remaining <= timedelta(minutes=WARN_THRESHOLD_MINUTES):
                    minutes_left = int(remaining.total_seconds() // 60)

                    # Send direct message to raid creator (ephemeral-like)
                    try:
                        await self.creator.send(
                            f"Warning! Only {minutes_left} minutes left until raid **{self.raid_name}** starts."
                        )
                    except Exception as e:
                        print(f"Error sending warning to {self.creator}: {e}")

                    # Also send to channel for reference
                    await channel.send(
                        f"{self.creator.mention} Warning! Only {minutes_left} minutes left until the raid starts."
                    )

            save_raid_to_db(self)
        return removed_any

    def remove_alt_by_sp(self, user_id: int, sp: str) -> bool:
        found = None
        for p in self.participants:
            if p.user_id == user_id and sp in [s.strip() for s in p.sp.split(",")] and (
                p.participant_type == "ALT" or (p.participant_type == "RESERVE" and p.reserve_for == "ALT")
            ):
                found = p
                break
        if found:
            self.participants.remove(found)
            if found.is_required_sp:
                for sp_item in [s.strip() for s in found.sp.split(",")]:
                    if sp_item.upper() in self.required_sps:
                        self.required_sps[sp_item.upper()] += 1
            self.fill_free_slots_from_reserve()
            save_raid_to_db(self)
            return True
        return False

    async def send_final_reminder(self):
        channel = self.bot.get_channel(self.channel_id)
        if channel:
            # Get mentions for all participants
            mentions = []
            for p in self.participants:
                if p.participant_type in ("MAIN", "ALT"):
                    mentions.append(f"<@{p.user_id}>")

            # Send direct messages to participants (ephemeral-like)
            for p in self.participants:
                if p.participant_type in ("MAIN", "ALT"):
                    member = self.guild.get_member(p.user_id)
                    if member:
                        try:
                            await member.send(f"**{self.raid_name}** is starting now!")
                        except Exception as e:
                            print(f"Error sending final reminder to {member}: {e}")

            # Also send to channel for reference
            await channel.send(f"**{self.raid_name}** is starting now! {' '.join(mentions)}")

            self.final_reminder_sent = True
            save_raid_to_db(self)

    async def notify_participants(self):
        channel = self.bot.get_channel(self.channel_id)
        if channel:
            # Get mentions for all participants
            mentions = []
            for p in self.participants:
                if p.participant_type in ("MAIN", "ALT"):
                    mentions.append(f"<@{p.user_id}>")

            # Calculate time until raid
            now = datetime.now(tz=self.raid_datetime.tzinfo)
            time_until = self.raid_datetime - now

            if time_until.total_seconds() > 0:
                hours, remainder = divmod(int(time_until.total_seconds()), 3600)
                minutes = remainder // 60

                time_str = ""
                if hours > 0:
                    time_str += f"{hours} hour{'s' if hours != 1 else ''} "
                if minutes > 0:
                    time_str += f"{minutes} minute{'s' if minutes != 1 else ''}"

                # Send direct messages to participants (ephemeral-like)
                for p in self.participants:
                    if p.participant_type in ("MAIN", "ALT"):
                        member = self.guild.get_member(p.user_id)
                        if member:
                            try:
                                await member.send(f"**{self.raid_name}** is starting in {time_str}!")
                            except Exception as e:
                                print(f"Error sending notification to {member}: {e}")

                # Also send to channel for reference
                await channel.send(f"**{self.raid_name}** is starting in {time_str}! {' '.join(mentions)}")

    def emojify_text(self, text: str):
        pattern = r":(\w+):"
        def rep(m):
            en = m.group(1)
            return self.emoji_map.get(en, m.group(0)) if hasattr(self, "emoji_map") else m.group(0)
        return re.sub(pattern, rep, text)

    def format_raid_list(self) -> str:
        main_alt = [p for p in self.participants if p.participant_type in ("MAIN", "ALT")]
        reserve = [p for p in self.participants if p.participant_type == "RESERVE"]
        lines = []
        lines.append(f"**{self.raid_name}** by <@{self.creator.id}>")
        if self.description:
            lines.append(f"*{self.description}*")
        lines.append(f"Date: {self.raid_datetime.strftime('%Y-%m-%d %H:%M %Z')}\n")
        for i in range(self.max_players):
            if i < len(main_alt):
                p = main_alt[i]
                mem = self.guild.get_member(p.user_id)
                disp = mem.mention if mem else f"User-{p.user_id}"
                sp_text = p.sp
                if not (sp_text.startswith(":") and sp_text.endswith(":")):
                    sp_text = f":{sp_text}:"
                sp_emoji = self.emojify_text(sp_text)
                level_info = f" [Lvl: {p.level_offset}]" if p.level_offset == 90 else ""
                lines.append(f"{i + 1}. {disp} {sp_emoji} ({p.participant_type}){level_info}")
            else:
                lines.append(f"{i + 1}. [Empty]")
        if reserve:
            lines.append("\n**Reserves:**")
            for p in reserve:
                mem = self.guild.get_member(p.user_id)
                disp = mem.mention if mem else f"User-{p.user_id}"
                sp_text = p.sp
                if not (sp_text.startswith(":") and sp_text.endswith(":")):
                    sp_text = f":{sp_text}:"
                sp_emoji = self.emojify_text(sp_text)
                rtype = f"Reserve({p.reserve_for})" if p.reserve_for else "Reserve"
                level_info = f" [Lvl: {p.level_offset}]" if p.level_offset != 0 else ""
                lines.append(f"- {disp} {sp_emoji} ({rtype}){level_info}")
        if self.required_sps:
            lines.append("\n**Required SPs Still Needed:**")
            for canon, cnt in self.required_sps.items():
                if cnt > 0:
                    orig = self.required_sps_original.get(canon, canon)
                    required_disp = self.emojify_text(f":{orig}:")
                    lines.append(f"- {required_disp}: {cnt}")
        if self.priority:
            now = datetime.now(tz=self.raid_datetime.tzinfo)
            time_left = self.raid_datetime - now
            if time_left > timedelta(hours=self.priority_hours):
                prio_remaining = time_left - timedelta(hours=self.priority_hours)
                hours, remainder = divmod(int(prio_remaining.total_seconds()), 3600)
                minutes = remainder // 60
                prio_info = f"Priority active for another {hours}h {minutes}m for roles: {self.prioritylist_str}"
            else:
                prio_info = "Priority period has ended."
            lines.append(f"\n**Priority Info:** {prio_info}")
        return "\n".join(lines)

    async def mention_on_creation(self):
        channel = self.bot.get_channel(self.channel_id)
        if not channel:
            return

        # Get members to mention
        members = []
        if self.priority:
            for rid in self.priority_roles:
                role = self.guild.get_role(rid)
                if role:
                    members.extend(role.members)
        else:
            for role_name in STANDARD_MENTION_ROLES:
                role = discord.utils.get(self.guild.roles, name=role_name)
                if role:
                    members.extend(role.members)

        if not members:
            return

        # Send direct messages to members (ephemeral-like)
        for member in members:
            try:
                await member.send(f"New raid created: **{self.raid_name}** on {self.raid_datetime.strftime('%Y-%m-%d %H:%M %Z')}!")
            except Exception as e:
                print(f"Error sending creation notification to {member}: {e}")

        # Split into chunks to avoid Discord's mention limit
        chunk_size = 20
        for i in range(0, len(members), chunk_size):
            chunk = members[i:i+chunk_size]
            mentions = " ".join(member.mention for member in chunk)

            # Send to channel for reference
            if self.priority:
                await self.track_bot_message(
                    await channel.send(f"{mentions} – A new PRIORITY raid was created: **{self.raid_name}**!")
                )
            else:
                await self.track_bot_message(
                    await channel.send(f"{mentions} – A new raid was created: **{self.raid_name}**!")
                )
