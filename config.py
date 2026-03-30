import os
from datetime import timedelta
from typing import List, Dict
from zoneinfo import ZoneInfo

# =====================================================
# Configuration & Constants
# =====================================================
ROLE_MARATO = "maratoniarz"
ROLE_CZLONEK = "członek"
ROLE_MLODY_CZLONEK = "młodszy członek"
ROLE_ALT_ALLOW = "alt_allow"
ROLE_REZERWA = 'rezerwa'

STANDARD_MENTION_ROLES = ["członek", "młodszy członek"]

SKILL_RANGE_DEFAULT = range(1, 12)
SKILL_RANGE_MSW = [1, 2, 3, 4, 9, 10, 11]

MARATONIARZ_THRESHOLD_HOURS = 10
NOTIFICATION_THRESHOLD_HOURS = 12
AUTO_PROMOTE_CHECK_MINUTES = 5
WARN_THRESHOLD_MINUTES = 180

NOTIFY_THRESHOLD = timedelta(hours=1)

DATETIME_FORMAT_1 = "%H:%M %Y-%m-%d"
DATETIME_FORMAT_2 = "%Y-%m-%d %H:%M"

TOKEN = os.getenv("DISCORD_TOKEN")

specializations = {
    "⚔️ Swordsman": [f":Sword_SP{i}:" for i in SKILL_RANGE_DEFAULT],
    "🏹 Archer": [f":Arch_SP{i}:" for i in SKILL_RANGE_DEFAULT],
    "🔮 Mage": [f":MAG_SP{i}:" for i in SKILL_RANGE_DEFAULT],
    "🥋 Martial Artist": [f":MSW_SP{i}:" for i in SKILL_RANGE_MSW],
}