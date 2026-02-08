import discord
from discord.ui import Button, View
from discord.ext import commands, tasks
from discord import app_commands
import random
import json
import os
from datetime import datetime, timedelta
import re
from collections import deque
from dotenv import load_dotenv

load_dotenv()
# ================== CONFIG ==================

TOKEN = 'MTQwNDkzMjc4NzEzMTI1NjkxOA.GJcUEe.9OEq6vNAMMFn9z476oMMU6iUB5nJkAphnjLSDg'
GUILD_ID = 1404912975181123584
VERIFIED_ROLE_ID = 1404919760617214067
CHANNEL_ID = 1465522308490723380          # Verification channel
RULES_CHANNEL_ID = 1465696442428690493    # Rules channel
SUGGESTIONS_CHANNEL_ID = 1465696442428690493  # Suggestions channel
LOG_CHANNEL_ID = 1465702979125645332      # Punishment log channel

LEVELS_FILE = "levels.json"
PUNISHMENTS_FILE = "punishments.json"

# Staff roles allowed to use moderation
STAFF_ROLE_IDS = {1404918192647700714, 1404915814267752609, 1465711817601974406}

# Color palette (lilac/purple theme)
COLOR_MAIN = 0x9b59b6
COLOR_DARK = 0x71368a
COLOR_ACCENT = 0xe91e63
COLOR_SUCCESS = 0x2ecc71
COLOR_INFO = 0x7289da
COLOR_WARNING = 0xf1c40f
COLOR_ERROR = 0xe74c3c
COLOR_PRIMARY = COLOR_MAIN  # Alias for compatibility




RAID_TIME_WINDOW = int(os.getenv('RAID_TIME_WINDOW', 10))  # segundos
RAID_MAX_JOINS = int(os.getenv('RAID_MAX_JOINS', 5))
RAID_ACCOUNT_MIN_AGE_DAYS = int(os.getenv('RAID_ACCOUNT_MIN_AGE_DAYS', 3))




join_tracker = deque()


# Level roles
LEVEL_ROLE_CONFIG = {
    5:  {"name": "Lvl 5 • Beginner", "color": COLOR_SUCCESS},
    10: {"name": "Lvl 10 • Regular",  "color": COLOR_INFO},
    20: {"name": "Lvl 20 • Veteran",  "color": COLOR_MAIN},
}

# ================== INTENTS & BOT ==================

intents = discord.Intents.default()
intents.members = True
intents.message_content = True

bot = commands.Bot(command_prefix="!", intents=intents)
tree = bot.tree  # slash commands

# ================== FILE HELPERS (LEVEL / PUNISHMENTS) ==================

def load_json(path: str, default: dict | list):
    if not os.path.exists(path):
        with open(path, "w", encoding="utf-8") as f:
            json.dump(default, f)
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)

def save_json(path: str, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=4)

# --- LEVEL ---

def load_levels():
    return load_json(LEVELS_FILE, {})

def save_levels(data):
    save_json(LEVELS_FILE, data)

def add_xp(user_id: int, amount: int = 5):
    data = load_levels()
    uid = str(user_id)
    if uid not in data:
        data[uid] = {"xp": 0, "level": 0}
    data[uid]["xp"] += amount
    new_level = data[uid]["xp"] // 100
    leveled_up = new_level > data[uid]["level"]
    data[uid]["level"] = new_level
    save_levels(data)
    return leveled_up, new_level

def get_level_info(user_id: int):
    data = load_levels()
    uid = str(user_id)
    if uid not in data:
        return 0, 0
    return data[uid]["level"], data[uid]["xp"]

async def ensure_level_role(guild: discord.Guild, level: int) -> discord.Role | None:
    cfg = LEVEL_ROLE_CONFIG.get(level)
    if not cfg:
        return None

    role_name = cfg["name"]
    role_color = discord.Color(cfg["color"])

    role = discord.utils.get(guild.roles, name=role_name)
    if role:
        return role

    role = await guild.create_role(
        name=role_name,
        colour=role_color,
        reason=f"Automatic level role (Level {level})"
    )
    return role

async def update_member_level_roles(member: discord.Member, level: int):
    guild = member.guild
    if level not in LEVEL_ROLE_CONFIG:
        return
    role_to_add = await ensure_level_role(guild, level)
    if not role_to_add:
        return
    if role_to_add not in member.roles:
        await member.add_roles(role_to_add, reason="Level up – automatic role")

# --- PUNISHMENTS / CASES ---

def load_punishments():
    return load_json(PUNISHMENTS_FILE, {"case_counter": 0, "users": {}})

def save_punishments(data):
    save_json(PUNISHMENTS_FILE, data)

def register_punishment(
    user_id: int,
    pun_type: str,
    moderator_id: int,
    reason: str,
    extra: dict | None = None
) -> tuple[int, dict]:
    data = load_punishments()
    data["case_counter"] += 1
    case_id = data["case_counter"]
    uid = str(user_id)
    if uid not in data["users"]:
        data["users"][uid] = {
            "warns": 0,
            "mutes": 0,
            "kicks": 0,
            "bans": 0,
            "cases": [],
            "mute_until": None
        }

    if pun_type in data["users"][uid]:
        data["users"][uid][pun_type] += 1

    entry = {
        "case_id": case_id,
        "type": pun_type,
        "moderator_id": moderator_id,
        "reason": reason,
        "timestamp": datetime.utcnow().isoformat()
    }
    if extra:
        entry.update(extra)
    data["users"][uid]["cases"].append(entry)
    save_punishments(data)
    return case_id, data["users"][uid]

def get_user_punishments(user_id: int) -> dict:
    data = load_punishments()
    return data["users"].get(str(user_id), {
        "warns": 0,
        "mutes": 0,
        "kicks": 0,
        "bans": 0,
        "cases": [],
        "mute_until": None
    })

def update_user_entry(user_id: int, new_data: dict):
    data = load_punishments()
    uid = str(user_id)
    data["users"][uid] = new_data
    save_punishments(data)

# ================== DURATION PARSER (10d 5h 30m 15s) ==================

time_regex = re.compile(r"(?P<value>\d+)\s*(?P<unit>[dhms])", re.IGNORECASE)

def parse_duration_to_timedelta(text: str) -> timedelta | None:
    text = text.strip().lower()
    matches = list(time_regex.finditer(text))
    if not matches:
        return None

    days = hours = minutes = seconds = 0
    for m in matches:
        value = int(m.group("value"))
        unit = m.group("unit")
        if unit == "d":
            days += value
        elif unit == "h":
            hours += value
        elif unit == "m":
            minutes += value
        elif unit == "s":
            seconds += value

    if days == hours == minutes == seconds == 0:
        return None
    return timedelta(days=days, hours=hours, minutes=minutes, seconds=seconds)

# ================== TRANSLATE VIEW ==================

class TranslateView(View):
    def __init__(self, english_text: str, portuguese_text: str):
        super().__init__(timeout=None)
        self.english_text = english_text
        self.portuguese_text = portuguese_text

    @discord.ui.button(
        label="🌐 Translate to Portuguese",
        style=discord.ButtonStyle.secondary,
        custom_id="translate_to_portuguese"
    )
    async def translate_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message(self.portuguese_text, ephemeral=True)

# ================== WELCOME / VERIFICATION ==================

WELCOME_MSGS = [
    "🚀 Welcome to Syntax's Back!!",
    "✨ You are now part of Syntax's Back!!",
    "🎉 Access granted to Syntax's Back!!",
    "🔥 Verification completed successfully!",
    "💎 All set, enjoy the server!",
]

EMOJIS_SUCCESS = ["✅", "🎉", "✨", "🚀", "🔥", "💎"]

class VerificationView(View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(
        label="🔐 Start OAuth2 Verification",
        style=discord.ButtonStyle.success,
        custom_id="start_oauth_verification"
    )
    async def start_oauth(self, interaction: discord.Interaction, button: discord.ui.Button):
        oauth_url = "https://lucky-syntaxverify.up.railway.app/login"  # Update with your Railway URL
        embed = discord.Embed(
            title="🔐 OAuth2 Verification Started",
            description=(
                "Click the link below to complete your verification via OAuth2.\n\n"
                "This will authorize your account and add you to the required servers.\n\n"
                f"[Authorize Here]({oauth_url})"
            ),
            color=COLOR_MAIN
        )
        embed.set_footer(text="Syntax's Back • Secure Verification")
        await interaction.response.send_message(embed=embed, ephemeral=True)

# ================== STAFF CHECKS ==================

def is_staff():
    async def predicate(ctx: commands.Context):
        if ctx.guild is None:
            return False
        user_roles = {r.id for r in ctx.author.roles}
        return any(rid in user_roles for rid in STAFF_ROLE_IDS)
    return commands.check(predicate)

def is_staff_interaction():
    async def predicate(interaction: discord.Interaction):
        if interaction.guild is None or not isinstance(interaction.user, discord.Member):
            return False
        user_roles = {r.id for r in interaction.user.roles}
        return any(rid in user_roles for rid in STAFF_ROLE_IDS)
    return app_commands.check(predicate)

async def send_log_embed(guild: discord.Guild, embed: discord.Embed):
    channel = guild.get_channel(LOG_CHANNEL_ID)
    if channel:
        await channel.send(embed=embed)

# ================== BASIC EVENTS ==================



@bot.event
async def on_member_join(member):
    now = datetime.utcnow()
    join_tracker.append(now)

    while join_tracker and (now - join_tracker[0]).seconds > RAID_TIME_WINDOW:
        join_tracker.popleft()

    account_age = (now - member.created_at).days

    if len(join_tracker) >= RAID_MAX_JOINS or account_age < RAID_ACCOUNT_MIN_AGE_DAYS:
        try:
            await member.kick(reason="Anti-Raid: Entrada suspeita")
        except:
            pass

        channel = discord.utils.get(member.guild.text_channels, name="logs")
        if channel:
            embed = discord.Embed(
                title="🚨 Anti-Raid ativado",
                description=(
                    f"Usuário: {member}\n"
                    f"Conta criada há: {account_age} dias\n"
                    f"Entradas recentes: {len(join_tracker)}"
                ),
                color=COLOR_ERROR
            )
            embed.timestamp = discord.utils.utcnow()
            await channel.send(embed=embed)




@bot.event
async def on_ready():
    print(f"{bot.user} online!")

    guild_obj = discord.Object(id=GUILD_ID)
    await tree.sync(guild=guild_obj)
    print("Slash commands synced.")

    verify_channel = bot.get_channel(CHANNEL_ID)
    if verify_channel:
        embed = discord.Embed(
            title="🔐 Syntax's Back • Secure OAuth2 Verification",
            description=(
                "Welcome to **Syntax's Back**! To ensure a safe and bot-free community, we use **OAuth2 verification**.\n\n"
                "This process authorizes your Discord account securely and adds you to the server automatically.\n\n"
                "```ini\n"
                "[ VERIFICATION STEPS ]\n"
                "1. Read the detailed rules below.\n"
                "2. Click 'Start OAuth2 Verification'.\n"
                "3. Authorize the app in the popup.\n"
                "4. You will be added to the server and verified instantly.\n"
                "```"
            ),
            color=COLOR_MAIN
        )
        embed.add_field(
            name="📘 Why verify?",
            value=(
                "• Prevents bots and spam accounts.\n"
                "• Ensures only real users join.\n"
                "• Protects our community from raids and abuse.\n"
                "• Uses Discord's official OAuth2 for security."
            ),
            inline=False
        )
        embed.add_field(
            name="🎉 Benefits after verification",
            value=(
                "• Full access to all channels.\n"
                "• Participate in chats, events, and giveaways.\n"
                "• Gain XP and level up by chatting.\n"
                "• Use slash commands like `/suggestion` and `/level`.\n"
                "• Enjoy our beautiful lilac/purple theme."
            ),
            inline=False
        )
        embed.add_field(
            name="📜 Detailed Rules Summary",
            value=(
                "**1. Respect & Behavior:** No insults, harassment, hate speech, or discrimination. "
                "Keep discussions civil.\n\n"
                "**2. Content Policy:** NSFW, illegal, or disturbing content is forbidden. "
                "Avoid toxic language.\n\n"
                "**3. Spam & Advertising:** No spamming messages, reactions, or links. "
                "External ads require staff approval.\n\n"
                "**4. Security & Privacy:** Never share personal data. "
                "Scams, phishing, or malicious activity leads to bans.\n\n"
                "**5. Staff Decisions:** Respect staff and their decisions. "
                "Appeal punishments calmly.\n\n"
                "**6. Channel Usage:** Use channels for their intended purpose. "
                "Read pins and descriptions."
            ),
            inline=False
        )
        embed.set_thumbnail(url="https://cdn.discordapp.com/emojis/1088000788191582538.png")
        embed.set_footer(text="Syntax's Back • Secure Verification System")
        embed.timestamp = discord.utils.utcnow()

        base_view = VerificationView()
        english_instructions = (
            "This embed provides detailed instructions for verifying your account.\n\n"
            "Verification uses OAuth2 to securely authorize your Discord account and add you to the server. "
            "After clicking 'Start OAuth2 Verification', a popup will appear for authorization. "
            "Once authorized, you will be added to the server with the Verified role, granting full access. "
            "Make sure to read the rules carefully before proceeding."
        )
        portuguese_instructions = (
            "Este embed fornece instruções detalhadas para verificar sua conta.\n\n"
            "A verificação usa OAuth2 para autorizar com segurança sua conta do Discord e adicioná-lo ao servidor. "
            "Após clicar em 'Iniciar Verificação OAuth2', um popup aparecerá para autorização. "
            "Uma vez autorizado, você será adicionado ao servidor com o cargo Verificado, concedendo acesso total. "
            "Certifique-se de ler as regras com cuidado antes de prosseguir."
        )
        translate_view = TranslateView(english_instructions, portuguese_instructions)
        base_view.add_item(translate_view.children[0])

        bot.add_view(base_view)
        await verify_channel.send(embed=embed, view=base_view)
        print("🔐 Detailed verification message sent!")

    rules_channel = bot.get_channel(RULES_CHANNEL_ID)
    if rules_channel:
        rules_embed = discord.Embed(
            title="📜 Official Rules – Syntax's Back",
            description=(
                "These rules apply to **all members** and are strictly enforced.\n"
                "Breaking them may result in mutes, kicks or permanent bans."
            ),
            color=COLOR_DARK
        )
        rules_embed.add_field(
            name="1️⃣ Respect and behavior",
            value=(
                "• No insults, harassment, hate speech or discrimination.\n"
                "• Debate is allowed, but keep it civil and friendly."
            ),
            inline=False
        )
        rules_embed.add_field(
            name="2️⃣ Content policy",
            value=(
                "• NSFW, illegal or disturbing content is strictly forbidden.\n"
                "• Avoid extremely toxic language and drama."
            ),
            inline=False
        )
        rules_embed.add_field(
            name="3️⃣ Spam & advertising",
            value=(
                "• Do not spam messages, reactions, mentions or links.\n"
                "• Advertising other servers or social media requires staff approval."
            ),
            inline=False
        )
        rules_embed.add_field(
            name="4️⃣ Security & privacy",
            value=(
                "• Never share personal data (yours or others') in public channels.\n"
                "• Any scam, phishing or malicious activity will lead to a ban."
            ),
            inline=False
        )
        rules_embed.add_field(
            name="5️⃣ Staff decisions",
            value=(
                "• Respect staff members and their decisions.\n"
                "• If you want to appeal a punishment, do it calmly and respectfully."
            ),
            inline=False
        )
        rules_embed.add_field(
            name="6️⃣ Use of channels",
            value=(
                "• Use each channel only for its intended topic.\n"
                "• Read pins and channel descriptions before chatting."
            ),
            inline=False
        )
        rules_embed.set_footer(
            text="Syntax's Back • By staying in the server, you agree with all rules."
        )
        rules_embed.timestamp = discord.utils.utcnow()

        await rules_channel.send(embed=rules_embed)
        print("📜 Rules sent in the rules channel!")

    auto_unmute_loop.start()

# ================== MODERATION (STAFF ONLY + LOGS + ESCALATION) ==================

async def apply_escalation(ctx: commands.Context, member: discord.Member, counts: dict):
    if counts["warns"] >= 3 and counts["mutes"] == 0:
        mute_cmd = bot.get_command("mute")
        if mute_cmd:
            await mute_cmd(ctx, member=member, reason="Automatic escalation: 3 accumulated warnings.")

    if counts["mutes"] >= 2 and counts["kicks"] == 0:
        kick_cmd = bot.get_command("kick")
        if kick_cmd:
            await kick_cmd(ctx, member=member, reason="Automatic escalation: multiple mutes.")

    if counts["kicks"] >= 2 and counts["bans"] == 0:
        ban_cmd = bot.get_command("ban")
        if ban_cmd:
            await ban_cmd(ctx, member=member, reason="Automatic escalation: multiple kicks.")

@bot.command()
@is_staff()
async def warn(ctx, member: discord.Member, *, reason: str = "No reason provided"):
    case_id, counts = register_punishment(member.id, "warns", ctx.author.id, reason)

    try:
        dm_embed = discord.Embed(
            title="⚠️ Warning issued",
            description=(
                f"You have received a **warning** in **{ctx.guild.name}**.\n\n"
                "```ini\n"
                "[ WARNING DETAILS ]\n"
                f"• Staff: {ctx.author}\n"
                f"• Reason: {reason}\n"
                f"• Case ID: #{case_id}\n"
                "```"
            ),
            color=COLOR_WARNING
        )
        dm_embed.set_footer(text="Syntax's Back • Moderation notice")
        await member.send(embed=dm_embed)
    except:
        pass

    public_embed = discord.Embed(
        title="⚠️ Member warned",
        description=(
            f"{member.mention} has received a **warning**.\n\n"
            "```ini\n"
            "[ SUMMARY ]\n"
            f"Moderator: {ctx.author}\n"
            f"Reason: {reason}\n"
            f"Case ID: #{case_id}\n"
            "```"
        ),
        color=COLOR_WARNING
    )
    public_embed.add_field(name="Total warnings for this user", value=str(counts["warns"]), inline=False)
    public_embed.set_footer(text="Syntax's Back • Moderation system")
    await ctx.send(embed=public_embed, delete_after=5)

    log_embed = discord.Embed(
        title="📘 LOG | WARNING",
        color=COLOR_WARNING
    )
    log_embed.add_field(name="User", value=f"{member} ({member.id})", inline=False)
    log_embed.add_field(name="Staff", value=f"{ctx.author} ({ctx.author.id})", inline=False)
    log_embed.add_field(name="Reason", value=reason, inline=False)
    log_embed.add_field(name="Case ID", value=f"#{case_id}", inline=True)
    log_embed.add_field(name="Total warnings", value=str(counts["warns"]), inline=True)
    log_embed.timestamp = discord.utils.utcnow()
    await send_log_embed(ctx.guild, log_embed)

    await apply_escalation(ctx, member, counts)




@bot.command(name="history")
@is_staff()
async def history(ctx, member: discord.Member):
    data = load_punishments()
    uid = str(member.id)

    if uid not in data["users"] or not data["users"][uid]["cases"]:
        await ctx.send("📭 Usuário sem histórico.")
        return

    embed = discord.Embed(
        title=f"📚 Histórico de punições",
        description=f"Usuário: {member} ({member.id})",
        color=COLOR_PRIMARY
    )

    for case in data["users"][uid]["cases"][-10:]:
        embed.add_field(
            name=f"Case #{case['case_id']} • {case['type'].upper()}",
            value=f"Motivo: {case['reason']}\nData: {case['timestamp']}",
            inline=False
        )

    embed.set_footer(text="Syntax's Back • Moderação")
    await ctx.send(embed=embed)



@bot.command(name="case")
@is_staff()
async def case_info(ctx, case_id: int):
    data = load_punishments()

    for uid, user_data in data["users"].items():
        for case in user_data.get("cases", []):
            if case["case_id"] == case_id:
                embed = discord.Embed(
                    title=f"📄 Case #{case_id}",
                    color=COLOR_PRIMARY
                )
                embed.add_field(name="Usuário ID", value=uid, inline=False)
                embed.add_field(name="Tipo", value=case["type"], inline=True)
                embed.add_field(name="Motivo", value=case["reason"], inline=False)
                embed.add_field(name="Staff ID", value=case["moderator_id"], inline=True)
                embed.add_field(name="Data", value=case["timestamp"], inline=True)
                embed.set_footer(text="Syntax's Back • Moderação")
                await ctx.send(embed=embed)
                return

    await ctx.send("❌ Case não encontrado.")




@bot.command()
@is_staff()
async def mute(ctx, member: discord.Member, duration: str | None = None, *, reason: str = "No reason provided"):
    """
    !mute @user reason
    !mute @user 10d reason
    !mute @user 5h reason
    !mute @user 30m reason
    !mute @user 15s reason
    """

    mute_role = discord.utils.get(ctx.guild.roles, name="Muted")
    if mute_role is None:
        mute_role = await ctx.guild.create_role(name="Muted", reason="Created for automatic mute system")
        for channel in ctx.guild.channels:
            try:
                await channel.set_permissions(mute_role, send_messages=False, speak=False, add_reactions=False)
            except:
                pass

    mute_until_iso = None
    duration_str = None

    if duration:
        td = parse_duration_to_timedelta(duration)
        if td is None:
            reason = f"{duration} {reason}" if reason != "No reason provided" else duration
        else:
            mute_until = datetime.utcnow() + td
            mute_until_iso = mute_until.isoformat()
            duration_str = duration

    await member.add_roles(mute_role, reason=reason)

    extra = {}
    if mute_until_iso:
        extra["mute_until"] = mute_until_iso
    if duration_str:
        extra["duration_str"] = duration_str

    case_id, counts = register_punishment(member.id, "mutes", ctx.author.id, reason, extra=extra)

    user_data = get_user_punishments(member.id)
    user_data["mute_until"] = mute_until_iso
    update_user_entry(member.id, user_data)

    try:
        dm_desc = (
            f"You have been **muted** in **{ctx.guild.name}**.\n\n"
            "```ini\n"
            "[ MUTE DETAILS ]\n"
            f"• Staff: {ctx.author}\n"
            f"• Reason: {reason}\n"
            f"• Case ID: #{case_id}\n"
        )
        if mute_until_iso:
            dm_desc += f"• Duration: {duration_str}\n"
        dm_desc += "```"

        dm_embed = discord.Embed(
            title="🔇 Mute applied",
            description=dm_desc,
            color=COLOR_ACCENT
        )
        dm_embed.set_footer(text="Syntax's Back • Moderation notice")
        await member.send(embed=dm_embed)
    except:
        pass

    public_desc = (
        f"{member.mention} has been **muted** in the server.\n\n"
        "```ini\n"
        "[ MUTE OVERVIEW ]\n"
        f"Staff: {ctx.author}\n"
        f"Reason: {reason}\n"
        f"Case ID: #{case_id}\n"
    )
    if mute_until_iso:
        public_desc += f"Duration: {duration_str}\n"
    public_desc += "```"

    public_embed = discord.Embed(
        title="🔇 User muted",
        description=public_desc,
        color=COLOR_ACCENT
    )
    public_embed.add_field(name="Total mutes for this user", value=str(counts["mutes"]), inline=False)
    if mute_until_iso:
        public_embed.add_field(name="Mute expires (UTC)", value=mute_until_iso, inline=False)
    public_embed.set_footer(text="Syntax's Back • Moderation system")
    await ctx.send(embed=public_embed, delete_after=5)

    log_embed = discord.Embed(
        title="📘 LOG | MUTE",
        color=COLOR_ACCENT
    )
    log_embed.add_field(name="User", value=f"{member} ({member.id})", inline=False)
    log_embed.add_field(name="Staff", value=f"{ctx.author} ({ctx.author.id})", inline=False)
    log_embed.add_field(name="Reason", value=reason, inline=False)
    log_embed.add_field(name="Case ID", value=f"#{case_id}", inline=True)
    if duration_str:
        log_embed.add_field(name="Duration", value=duration_str, inline=True)
    if mute_until_iso:
        log_embed.add_field(name="Mute until (UTC)", value=mute_until_iso, inline=False)
    log_embed.add_field(name="Total mutes", value=str(counts["mutes"]), inline=True)
    log_embed.timestamp = discord.utils.utcnow()
    await send_log_embed(ctx.guild, log_embed)

    await apply_escalation(ctx, member, counts)

@bot.command()
@is_staff()
async def kick(ctx, member: discord.Member, *, reason: str = "No reason provided"):
    case_id, counts = register_punishment(member.id, "kicks", ctx.author.id, reason)

    try:
        dm_embed = discord.Embed(
            title="👢 You have been kicked",
            description=(
                f"You were **kicked** from **{ctx.guild.name}**.\n\n"
                "```ini\n"
                "[ KICK DETAILS ]\n"
                f"• Staff: {ctx.author}\n"
                f"• Reason: {reason}\n"
                f"• Case ID: #{case_id}\n"
                "```"
            ),
            color=COLOR_ERROR
        )
        dm_embed.set_footer(text="Syntax's Back • Moderation notice")
        await member.send(embed=dm_embed)
    except:
        pass

    await member.kick(reason=reason)

    public_embed = discord.Embed(
        title="👢 User kicked",
        description=(
            f"{member.mention} has been **kicked** from the server.\n\n"
            "```ini\n"
            "[ SUMMARY ]\n"
            f"Staff: {ctx.author}\n"
            f"Reason: {reason}\n"
            f"Case ID: #{case_id}\n"
            "```"
        ),
        color=COLOR_ERROR
    )
    public_embed.add_field(name="Total kicks for this user", value=str(counts["kicks"]), inline=False)
    public_embed.set_footer(text="Syntax's Back • Moderation system")
    await ctx.send(embed=public_embed, delete_after=5)

    log_embed = discord.Embed(
        title="📘 LOG | KICK",
        color=COLOR_ERROR
    )
    log_embed.add_field(name="User", value=f"{member} ({member.id})", inline=False)
    log_embed.add_field(name="Staff", value=f"{ctx.author} ({ctx.author.id})", inline=False)
    log_embed.add_field(name="Reason", value=reason, inline=False)
    log_embed.add_field(name="Case ID", value=f"#{case_id}", inline=True)
    log_embed.add_field(name="Total kicks", value=str(counts["kicks"]), inline=True)
    log_embed.timestamp = discord.utils.utcnow()
    await send_log_embed(ctx.guild, log_embed)

    await apply_escalation(ctx, member, counts)

@bot.command()
@is_staff()
async def ban(ctx, member: discord.Member, *, reason: str = "No reason provided"):
    case_id, counts = register_punishment(member.id, "bans", ctx.author.id, reason)

    try:
        dm_embed = discord.Embed(
            title="⛔ You have been banned",
            description=(
                f"You were **banned** from **{ctx.guild.name}**.\n\n"
                "```ini\n"
                "[ BAN DETAILS ]\n"
                f"• Staff: {ctx.author}\n"
                f"• Reason: {reason}\n"
                f"• Case ID: #{case_id}\n"
                "```"
            ),
            color=COLOR_ERROR
        )
        dm_embed.set_footer(text="Syntax's Back • Moderation notice")
        await member.send(embed=dm_embed)
    except:
        pass

    await member.ban(reason=reason)

    public_embed = discord.Embed(
        title="⛔ User banned",
        description=(
            f"{member.mention} has been **banned** from the server.\n\n"
            "```ini\n"
            "[ SUMMARY ]\n"
            f"Staff: {ctx.author}\n"
            f"Reason: {reason}\n"
            f"Case ID: #{case_id}\n"
            "```"
        ),
        color=COLOR_ERROR
    )
    public_embed.add_field(name="Total bans for this user", value=str(counts["bans"]), inline=False)
    public_embed.set_footer(text="Syntax's Back • Moderation system")
    await ctx.send(embed=public_embed, delete_after=5)

    log_embed = discord.Embed(
        title="📘 LOG | BAN",
        color=COLOR_ERROR
    )
    log_embed.add_field(name="User", value=f"{member} ({member.id})", inline=False)
    log_embed.add_field(name="Staff", value=f"{ctx.author} ({ctx.author.id})", inline=False)
    log_embed.add_field(name="Reason", value=reason, inline=False)
    log_embed.add_field(name="Case ID", value=f"#{case_id}", inline=True)
    log_embed.add_field(name="Total bans", value=str(counts["bans"]), inline=True)
    log_embed.timestamp = discord.utils.utcnow()
    await send_log_embed(ctx.guild, log_embed)

# ==== MANUAL UNMUTE ====

@bot.command()
@is_staff()
async def unmute(ctx, member: discord.Member, *, reason: str = "No reason provided"):
    mute_role = discord.utils.get(ctx.guild.roles, name="Muted")
    if mute_role is None or mute_role not in member.roles:
        await ctx.send(
            embed=discord.Embed(
                title="ℹ️ No active mute",
                description=(
                    f"{member.mention} does not currently have the **Muted** role.\n"
                    "Nothing to unmute."
                ),
                color=COLOR_INFO
            ),
            delete_after=5
        )
        return

    await member.remove_roles(mute_role, reason=reason)

    user_data = get_user_punishments(member.id)
    user_data["mute_until"] = None
    update_user_entry(member.id, user_data)

    try:
        dm_embed = discord.Embed(
            title="🔊 You have been unmuted",
            description=(
                f"Your mute in **{ctx.guild.name}** has been removed.\n\n"
                "```ini\n"
                "[ UNMUTE DETAILS ]\n"
                f"• Staff: {ctx.author}\n"
                f"• Reason: {reason}\n"
                "```"
            ),
            color=COLOR_SUCCESS
        )
        dm_embed.set_footer(text="Syntax's Back • Moderation notice")
        await member.send(embed=dm_embed)
    except:
        pass

    public_embed = discord.Embed(
        title="🔊 User unmuted",
        description=(
            f"{member.mention} has been **unmuted**.\n\n"
            "```ini\n"
            "[ SUMMARY ]\n"
            f"Staff: {ctx.author}\n"
            f"Reason: {reason}\n"
            "```"
        ),
        color=COLOR_SUCCESS
    )
    public_embed.set_footer(text="Syntax's Back • Moderation system")
    await ctx.send(embed=public_embed, delete_after=5)

    log_embed = discord.Embed(
        title="📘 LOG | UNMUTE",
        color=COLOR_SUCCESS
    )
    log_embed.add_field(name="User", value=f"{member} ({member.id})", inline=False)
    log_embed.add_field(name="Staff", value=f"{ctx.author} ({ctx.author.id})", inline=False)
    log_embed.add_field(name="Reason", value=reason, inline=False)
    log_embed.timestamp = discord.utils.utcnow()
    await send_log_embed(ctx.guild, log_embed)

# ==== RESET PUNISHMENTS ====

@bot.command(name="resetpunishments")
@is_staff()
async def reset_punishments_cmd(ctx, member: discord.Member):
    data = load_punishments()
    uid = str(member.id)
    if uid not in data["users"]:
        await ctx.send(
            embed=discord.Embed(
                title="ℹ️ No punishment history",
                description=(
                    f"{member.mention} has no stored punishment records.\n"
                    "Nothing to reset."
                ),
                color=COLOR_INFO
            ),
            delete_after=5
        )
        return

    old = data["users"][uid]
    data["users"][uid] = {
        "warns": 0,
        "mutes": 0,
        "kicks": 0,
        "bans": 0,
        "cases": [],
        "mute_until": None
    }
    save_punishments(data)

    public_embed = discord.Embed(
        title="🧹 Punishment history cleared",
        description=(
            f"All punishment history for {member.mention} has been **reset**.\n\n"
            "```ini\n"
            "[ PREVIOUS COUNTS ]\n"
            f"• Warns: {old.get('warns', 0)}\n"
            f"• Mutes: {old.get('mutes', 0)}\n"
            f"• Kicks: {old.get('kicks', 0)}\n"
            f"• Bans: {old.get('bans', 0)}\n"
            "```"
        ),
        color=COLOR_DARK
    )
    public_embed.set_footer(text="Syntax's Back • Moderation system")
    await ctx.send(embed=public_embed, delete_after=5)

    log_embed = discord.Embed(
        title="📘 LOG | RESET PUNISHMENTS",
        color=COLOR_DARK
    )
    log_embed.add_field(name="User", value=f"{member} ({member.id})", inline=False)
    log_embed.add_field(name="Staff", value=f"{ctx.author} ({ctx.author.id})", inline=False)
    log_embed.add_field(
        name="Cleared records",
        value=(
            f"Warns: {old.get('warns', 0)}, "
            f"Mutes: {old.get('mutes', 0)}, "
            f"Kicks: {old.get('kicks', 0)}, "
            f"Bans: {old.get('bans', 0)}"
        ),
        inline=False
    )
    log_embed.timestamp = discord.utils.utcnow()
    await send_log_embed(ctx.guild, log_embed)

# ================== NOVOS COMANDOS: CLEAR / SLOWMODE / UNBAN / LOCK / UNLOCK ==================

@bot.command(name="clear")
@is_staff()
async def clear(ctx: commands.Context, quantidade: int):
    """Limpa uma quantidade de mensagens no canal atual (máx. 100)."""
    if quantidade <= 0:
        await ctx.send(
            embed=discord.Embed(
                title="Valor inválido",
                description="Informe uma quantidade **maior que 0**.",
                color=COLOR_ERROR
            ),
            delete_after=5
        )
        return

    if quantidade > 100:
        quantidade = 100

    deleted = await ctx.channel.purge(limit=quantidade + 1)
    deletadas = max(len(deleted) - 1, 0)

    embed = discord.Embed(
        title="🧹 Chat limpo",
        description=f"Foram apagadas **{deletadas}** mensagens neste canal.",
        color=COLOR_INFO
    )
    embed.set_footer(text="Syntax's Back • Ferramentas de staff")
    await ctx.send(embed=embed, delete_after=5)

@bot.command(name="slowmode")
@is_staff()
async def slowmode(ctx: commands.Context, segundos: int):
    """Define o slowmode do canal atual em segundos (0 para remover)."""
    if segundos < 0:
        await ctx.send(
            embed=discord.Embed(
                title="Valor inválido",
                description="O tempo de slowmode **não pode ser negativo**.",
                color=COLOR_ERROR
            ),
            delete_after=5
        )
        return

    if segundos > 21600:
        segundos = 21600

    await ctx.channel.edit(slowmode_delay=segundos)

    if segundos == 0:
        desc = "O slowmode deste canal foi **removido**."
    else:
        desc = f"O slowmode deste canal foi definido para **{segundos} segundos**."

    embed = discord.Embed(
        title="⏱️ Slowmode atualizado",
        description=desc,
        color=COLOR_INFO
    )
    embed.set_footer(text="Syntax's Back • Ferramentas de staff")
    await ctx.send(embed=embed, delete_after=5)

@bot.command(name="unban")
@is_staff()
async def unban(ctx: commands.Context, *, user: str):
    """
    Desbane um usuário pelo ID ou nome#tag.
    Ex:
    !unban 123456789012345678
    !unban Fulano#0001
    """
    bans = ctx.guild.bans()  # Removido await: é um async iterator
    alvo = None

    if user.isdigit():
        uid = int(user)
        async for entry in bans:  # Usar async for
            if entry.user.id == uid:
                alvo = entry.user
                break
    else:
        nome, sep, discrim = user.partition("#")
        if sep:
            async for entry in bans:  # Usar async for
                if entry.user.name == nome and entry.user.discriminator == discrim:
                    alvo = entry.user
                    break

    if alvo is None:
        await ctx.send(
            embed=discord.Embed(
                title="Usuário não encontrado",
                description="Não achei esse usuário na lista de banidos.",
                color=COLOR_ERROR
            ),
            delete_after=5
        )
        return

    await ctx.guild.unban(alvo, reason=f"Unban manual por {ctx.author}")
    embed = discord.Embed(
        title="✅ Usuário desbanido",
        description=f"O usuário **{alvo}** foi desbanido com sucesso.",
        color=COLOR_SUCCESS
    )
    embed.set_footer(text="Syntax's Back • Moderação")
    await ctx.send(embed=embed, delete_after=5)

@bot.command(name="modlogs")
@is_staff()
async def modlogs(ctx: commands.Context, user_id: int):
    data = load_punishments()
    uid = str(user_id)

    if uid not in data["users"] or not data["users"][uid]["cases"]:
        embed = discord.Embed(
            title="📁 Mod Logs • Histórico de Moderação",
            description=(
                "Nenhum registro de punição foi encontrado para este usuário.\n\n"
                "```ini\n"
                "[ STATUS ]\n"
                "✔ Usuário sem histórico disciplinar\n"
                f"ID: {user_id}\n"
                "```"
            ),
            color=COLOR_SUCCESS
        )
        embed.set_footer(text="Syntax's Back • Sistema de Moderação")
        embed.timestamp = discord.utils.utcnow()
        await ctx.send(embed=embed)
        return

    user_data = data["users"][uid]
    cases = user_data["cases"]

    embed = discord.Embed(
        title="📁 Mod Logs • Histórico de Moderação",
        description=(
            "```ini\n"
            "[ RESUMO GERAL ]\n"
            f"Warns: {user_data.get('warns', 0)}\n"
            f"Mutes: {user_data.get('mutes', 0)}\n"
            f"Kicks: {user_data.get('kicks', 0)}\n"
            f"Bans:  {user_data.get('bans', 0)}\n"
            f"Total de casos: {len(cases)}\n"
            "```"
        ),
        color=COLOR_DARK
    )

    embed.add_field(
        name="👤 Usuário",
        value=(
            "```ini\n"
            f"ID: {user_id}\n"
            "```"
        ),
        inline=False
    )

    for case in cases[-10:]:
        moderator = ctx.guild.get_member(case["moderator_id"])
        mod_name = (
            f"{moderator} ({moderator.id})"
            if moderator
            else f"ID {case['moderator_id']}"
        )

        raw_time = case.get("timestamp", "Unknown")
        try:
            formatted_time = datetime.fromisoformat(raw_time).strftime("%d/%m/%Y • %H:%M UTC")
        except:
            formatted_time = raw_time

        embed.add_field(
            name=f"📌 Case #{case['case_id']} • {case['type'].upper()}",
            value=(
                "```ini\n"
                f"Staff: {mod_name}\n"
                f"Motivo: {case.get('reason', 'Não informado')}\n"
                f"Data: {formatted_time}\n"
                "```"
            ),
            inline=False
        )

    embed.set_footer(
        text=f"Solicitado por {ctx.author} • Syntax's Back • Moderação"
    )
    embed.timestamp = discord.utils.utcnow()

    await ctx.send(embed=embed)
@bot.command(name="reason")
@is_staff()
async def change_reason(ctx: commands.Context, case_number: int, *, new_reason: str):
    data = load_punishments()
    found = False
    target_user_id = None
    old_reason = None
    target_case = None

    # Buscar o case em todos os usuários
    for uid, user_data in data.get("users", {}).items():
        for case in user_data.get("cases", []):
            if case.get("case_id") == case_number:
                old_reason = case.get("reason", "Não informado")
                case["reason"] = new_reason
                target_user_id = uid
                target_case = case
                found = True
                break
        if found:
            break

    if not found:
        embed = discord.Embed(
            title="❌ Case não encontrado",
            description=(
                "Não foi possível localizar o case informado.\n\n"
                "```ini\n"
                "[ ERRO ]\n"
                f"Case ID: {case_number}\n"
                "Status: INEXISTENTE\n"
                "```"
            ),
            color=COLOR_ERROR
        )
        embed.set_footer(text="Syntax's Back • Sistema de Moderação")
        embed.timestamp = discord.utils.utcnow()
        await ctx.send(embed=embed)
        return

    # Salvar alteração
    save_punishments(data)

    # Embed público
    embed = discord.Embed(
        title="✏️ Motivo de punição alterado",
        description=(
            "O motivo da punição foi atualizado com sucesso.\n\n"
            "```ini\n"
            "[ ALTERAÇÃO DE CASE ]\n"
            f"Case ID: {case_number}\n"
            f"Usuário ID: {target_user_id}\n"
            f"Staff: {ctx.author} ({ctx.author.id})\n"
            "```"
        ),
        color=COLOR_INFO
    )

    embed.add_field(
        name="📄 Motivo antigo",
        value=f"```{old_reason}```",
        inline=False
    )

    embed.add_field(
        name="📝 Novo motivo",
        value=f"```{new_reason}```",
        inline=False
    )

    embed.set_footer(text="Syntax's Back • Moderação")
    embed.timestamp = discord.utils.utcnow()

    await ctx.send(embed=embed)

    # Log embed
    log_embed = discord.Embed(
        title="📘 LOG | CASE EDITADO",
        color=COLOR_INFO
    )

    log_embed.add_field(name="Case ID", value=f"#{case_number}", inline=True)
    log_embed.add_field(name="Usuário ID", value=str(target_user_id), inline=True)
    log_embed.add_field(name="Staff", value=f"{ctx.author} ({ctx.author.id})", inline=False)
    log_embed.add_field(name="Motivo antigo", value=old_reason, inline=False)
    log_embed.add_field(name="Novo motivo", value=new_reason, inline=False)

    log_embed.timestamp = discord.utils.utcnow()
    await send_log_embed(ctx.guild, log_embed)

@bot.command(name="lock")
@is_staff()
async def lock(ctx: commands.Context):
    """Tranca o canal atual para @everyone."""
    overwrite = ctx.channel.overwrites_for(ctx.guild.default_role)
    overwrite.send_messages = False
    await ctx.channel.set_permissions(ctx.guild.default_role, overwrite=overwrite)

    embed = discord.Embed(
        title="🔒 Canal trancado",
        description="Este canal foi **trancado** para `@everyone`.",
        color=COLOR_WARNING
    )
    embed.set_footer(text="Syntax's Back • Moderação")
    await ctx.send(embed=embed, delete_after=5)

@bot.command(name="unlock")
@is_staff()
async def unlock(ctx: commands.Context):
    """Destranca o canal atual para @everyone."""
    overwrite = ctx.channel.overwrites_for(ctx.guild.default_role)
    overwrite.send_messages = True
    await ctx.channel.set_permissions(ctx.guild.default_role, overwrite=overwrite)

    embed = discord.Embed(
        title="🔓 Canal destrancado",
        description="Este canal foi **destrancado** para `@everyone`.",
        color=COLOR_SUCCESS
    )
    embed.set_footer(text="Syntax's Back • Moderação")
    await ctx.send(embed=embed, delete_after=5)

# ================== AUTO UNMUTE LOOP ==================

@tasks.loop(seconds=30)
async def auto_unmute_loop():
    data = load_punishments()
    changed = False
    now = datetime.utcnow()

    for uid, info in data.get("users", {}).items():
        mute_until_iso = info.get("mute_until")
        if not mute_until_iso:
            continue
        try:
            mute_until = datetime.fromisoformat(mute_until_iso)
        except Exception:
            continue

        if now >= mute_until:
            guild = bot.get_guild(GUILD_ID)
            if not guild:
                continue
            member = guild.get_member(int(uid))
            if not member:
                continue

            mute_role = discord.utils.get(guild.roles, name="Muted")
            if mute_role and mute_role in member.roles:
                try:
                    await member.remove_roles(mute_role, reason="Automatic mute expiration")
                except:
                    pass

                info["mute_until"] = None
                changed = True

                log_embed = discord.Embed(
                    title="📘 LOG | AUTO UNMUTE",
                    description=(
                        "```ini\n"
                        "[ AUTO UNMUTE ]\n"
                        f"User: {member} ({member.id})\n"
                        "Reason: Mute duration expired\n"
                        "```"
                    ),
                    color=COLOR_SUCCESS
                )
                log_embed.timestamp = discord.utils.utcnow()
                await send_log_embed(guild, log_embed)

    if changed:
        save_punishments(data)

@auto_unmute_loop.before_loop
async def before_auto_unmute_loop():
    await bot.wait_until_ready()

# ================== LEVELING + ROLES ==================

@bot.event
async def on_message(message: discord.Message):
    if message.author.bot or not message.guild:
        return

    leveled_up, new_level = add_xp(message.author.id, amount=5)
    if leveled_up and new_level > 0:
        await update_member_level_roles(message.author, new_level)
        embed = discord.Embed(
            title="📈 Level Up!",
            description=(
                f"{message.author.mention} has reached **level {new_level}**!\n\n"
                "```ini\n"
                "[ PROGRESS INFO ]\n"
                "Keep chatting to gain XP and unlock new roles.\n"
                "```"
            ),
            color=COLOR_MAIN
        )
        embed.set_thumbnail(url=message.author.display_avatar.url)
        embed.set_footer(text="Syntax's Back • Leveling system")
        await message.channel.send(embed=embed, delete_after=5)

    await bot.process_commands(message)

# ================== SLASH COMMANDS – MEMBERS ==================

@tree.command(name="level", description="Shows your or another member's level and XP.", guild=discord.Object(id=GUILD_ID))
async def slash_level(interaction: discord.Interaction, member: discord.Member | None = None):
    member = member or interaction.user
    level_value, xp_value = get_level_info(member.id)

    embed = discord.Embed(
        title=f"🎮 Level panel – {member.display_name}",
        description=(
            "```ini\n"
            "[ LEVEL DATA ]\n"
            f"• Current level: {level_value}\n"
            f"• Total XP: {xp_value}\n"
            "```"
        ),
        color=COLOR_INFO
    )
    embed.set_thumbnail(url=member.display_avatar.url)
    embed.add_field(
        name="How to gain XP?",
        value=(
            "• Talk in chat.\n"
            "• Be active in the community.\n"
            "• Participate in events and discussions."
        ),
        inline=False
    )
    embed.set_footer(text="Syntax's Back • Leveling overview")
    await interaction.response.send_message(embed=embed, ephemeral=True)

@tree.command(name="suggestion", description="Send a suggestion to the server.", guild=discord.Object(id=GUILD_ID))
async def slash_suggestion(interaction: discord.Interaction, text: str):
    channel = interaction.client.get_channel(SUGGESTIONS_CHANNEL_ID)
    if channel is None:
        await interaction.response.send_message("Suggestions channel is not configured correctly.", ephemeral=True)
        return

    embed = discord.Embed(
        title="💡 New Suggestion",
        description=(
            f"{text}\n\n"
            "```ini\n"
            "[ SUGGESTION INFO ]\n"
            f"Author: {interaction.user}\n"
            "Vote with the reactions below.\n"
            "```"
        ),
        color=COLOR_MAIN
    )
    embed.set_author(name=f"Suggested by {interaction.user}", icon_url=interaction.user.display_avatar.url)
    embed.set_footer(text="Syntax's Back • Community feedback")

    msg = await channel.send(embed=embed)
    await msg.add_reaction("✅")
    await msg.add_reaction("❌")

    confirm = discord.Embed(
        title="✅ Suggestion sent",
        description=(
            "Your suggestion was successfully posted in the **suggestions channel**.\n\n"
            "Thank you for helping to improve the server!"
        ),
        color=COLOR_SUCCESS
    )
    confirm.set_footer(text="Syntax's Back • Suggestions")
    await interaction.response.send_message(embed=confirm, ephemeral=True)

# ================== SLASH COMMAND /cmds (STAFF ONLY) ==================

@tree.command(name="cmds", description="Show all available commands and what they do.", guild=discord.Object(id=GUILD_ID))
@is_staff_interaction()
async def slash_cmds(interaction: discord.Interaction):
    embed = discord.Embed(
        title="📚 Command Reference – Syntax's Back",
        description=(
            "This panel lists the **main commands** available in the server.\n"
            "Moderation commands are restricted to **staff roles**."
        ),
        color=COLOR_DARK
    )

    embed.add_field(
        name="Moderation (prefix `!`)",
        value=(
            "```ini\n"
            "[ PREFIX COMMANDS ]\n"
            "!warn @user [reason]\n"
            "    -> Add a warning and log a case.\n\n"
            "!mute @user [duration] [reason]\n"
            "    -> Mute a user. Duration examples: 10d, 5h, 30m, 15s.\n\n"
            "!unmute @user [reason]\n"
            "    -> Remove the Muted role and clear mute timer.\n\n"
            "!kick @user [reason]\n"
            "    -> Kick the user from the server.\n\n"
            "!ban @user [reason]\n"
            "    -> Ban the user from the server.\n\n"
            "!resetpunishments @user\n"
            "    -> Clear all punishment history of a user.\n\n"
            "!clear <amount>\n"
            "    -> Clear messages in the current channel.\n\n"
            "!slowmode <seconds>\n"
            "    -> Set or remove slowmode in the channel.\n\n"
            "!unban <id or name#tag>\n"
            "    -> Unban a user.\n\n"
            "!lock / !unlock\n"
            "    -> Lock or unlock the current channel.\n"
            "```"
        ),
        inline=False
    )

    embed.add_field(
        name="Slash commands",
        value=(
            "```ini\n"
            "[ SLASH COMMANDS ]\n"
            "/level [user]\n"
            "    -> Show level and XP.\n\n"
            "/suggestion <text>\n"
            "    -> Send a suggestion to the suggestions channel.\n\n"
            "/cmds\n"
            "    -> Show this staff-only command panel.\n"
            "```"
        ),
        inline=False
    )

    embed.add_field(
        name="Automatic systems",
        value=(
            "```ini\n"
            "[ AUTOMATION ]\n"
            "• Escalation:\n"
            "    3 warns  -> mute\n"
            "    2 mutes  -> kick\n"
            "    2 kicks  -> ban\n\n"
            "• Auto-unmute:\n"
            "    Temporary mutes are automatically removed when time expires.\n\n"
            "• Chat cleanup:\n"
            "    Public moderation messages are auto-deleted after 5 seconds.\n"
            "```"
        ),
        inline=False
    )

    embed.set_footer(text="Syntax's Back • Staff tools overview")
    embed.timestamp = discord.utils.utcnow()

    await interaction.response.send_message(embed=embed, ephemeral=True)

# ================== START ==================

bot.run(TOKEN)
