import os
import discord
from discord.ext import commands
from discord import app_commands, Embed
from discord.ui import View, Button
from dotenv import load_dotenv
import sqlite3
from datetime import datetime, timedelta, timezone
import re
import json
from keep_alive import keep_alive

import asyncio


# ---------------- Setup ----------------
load_dotenv()
TOKEN = os.getenv("DISCORD_TOKEN")
if not TOKEN:
    raise SystemExit("DISCORD_TOKEN not found in .env")

keep_alive()

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "bot_data.db")
BAD_WORDS_FILE = "server_bad_words.json"


# ---------------- Profanity & Links ----------------
profanity = {"poopoo"}
link_regex = re.compile(r"https?://\S+|www\.\S+", re.IGNORECASE)

# ---------------- Bot ----------------
intents = discord.Intents.all()
bot = commands.Bot(command_prefix="!", intents=intents)
tree = bot.tree

status_list = [
    "/help | Protecting your server",
    "Watching over warnings",
    "Filtering bad words",
    "Managing join messages & roles"
]

async def change_status():
    await bot.wait_until_ready()
    while not bot.is_closed():
        for status in status_list:
            await bot.change_presence(activity=discord.Activity(type=discord.ActivityType.playing, name=status))
            await asyncio.sleep(15)

bot.loop.create_task(change_status())

# ---------------- Database ----------------
def create_tables():
    with sqlite3.connect(DB_PATH) as conn:
        cur = conn.cursor()
        cur.execute("""
            CREATE TABLE IF NOT EXISTS users_per_guild (
                user_id INTEGER,
                guild_id INTEGER,
                warning_count INTEGER,
                PRIMARY KEY(user_id, guild_id)
            )
        """)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS join_messages (
                guild_id INTEGER PRIMARY KEY,
                message TEXT
            )
        """)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS join_channels (
                guild_id INTEGER PRIMARY KEY,
                channel_id INTEGER
            )
        """)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS auto_roles (
                guild_id INTEGER,
                role_id INTEGER,
                PRIMARY KEY(guild_id, role_id)
            )
        """)
        conn.commit()
create_tables()

# ---------------- Warnings ----------------
def increase_and_get_warnings(user_id: int, guild_id: int):
    with sqlite3.connect(DB_PATH) as conn:
        cur = conn.cursor()
        cur.execute("SELECT warning_count FROM users_per_guild WHERE user_id=? AND guild_id=?", (user_id, guild_id))
        result = cur.fetchone()
        if not result:
            cur.execute("INSERT INTO users_per_guild VALUES (?, ?, 1)", (user_id, guild_id))
            conn.commit()
            return 1
        new_count = result[0] + 1
        cur.execute("UPDATE users_per_guild SET warning_count=? WHERE user_id=? AND guild_id=?", (new_count, user_id, guild_id))
        conn.commit()
        return new_count

def get_warnings(user_id: int, guild_id: int):
    with sqlite3.connect(DB_PATH) as conn:
        cur = conn.cursor()
        cur.execute("SELECT warning_count FROM users_per_guild WHERE user_id=? AND guild_id=?", (user_id, guild_id))
        result = cur.fetchone()
        return result[0] if result else 0

def reset_warnings(user_id: int, guild_id: int):
    with sqlite3.connect(DB_PATH) as conn:
        cur = conn.cursor()
        cur.execute("DELETE FROM users_per_guild WHERE user_id=? AND guild_id=?", (user_id, guild_id))
        conn.commit()

# ---------------- Join Messages & Roles ----------------
def set_join_message(guild_id, message):
    with sqlite3.connect(DB_PATH) as conn:
        cur = conn.cursor()
        cur.execute("REPLACE INTO join_messages (guild_id, message) VALUES (?, ?)", (guild_id, message))
        conn.commit()

def remove_join_message(guild_id):
    with sqlite3.connect(DB_PATH) as conn:
        cur = conn.cursor()
        cur.execute("DELETE FROM join_messages WHERE guild_id=?", (guild_id,))
        conn.commit()

def get_join_message(guild_id):
    with sqlite3.connect(DB_PATH) as conn:
        cur = conn.cursor()
        cur.execute("SELECT message FROM join_messages WHERE guild_id=?", (guild_id,))
        result = cur.fetchone()
        return result[0] if result else None

def set_join_channel(guild_id, channel_id):
    with sqlite3.connect(DB_PATH) as conn:
        cur = conn.cursor()
        cur.execute("REPLACE INTO join_channels (guild_id, channel_id) VALUES (?, ?)", (guild_id, channel_id))
        conn.commit()

def get_join_channel(guild_id):
    with sqlite3.connect(DB_PATH) as conn:
        cur = conn.cursor()
        cur.execute("SELECT channel_id FROM join_channels WHERE guild_id=?", (guild_id,))
        result = cur.fetchone()
        return result[0] if result else None

def add_auto_role(guild_id, role_id):
    with sqlite3.connect(DB_PATH) as conn:
        cur = conn.cursor()
        cur.execute("INSERT OR IGNORE INTO auto_roles (guild_id, role_id) VALUES (?, ?)", (guild_id, role_id))
        conn.commit()

def remove_auto_role_db(guild_id, role_id):
    with sqlite3.connect(DB_PATH) as conn:
        cur = conn.cursor()
        cur.execute("DELETE FROM auto_roles WHERE guild_id=? AND role_id=?", (guild_id, role_id))
        conn.commit()

def get_auto_roles(guild_id):
    with sqlite3.connect(DB_PATH) as conn:
        cur = conn.cursor()
        cur.execute("SELECT role_id FROM auto_roles WHERE guild_id=?", (guild_id,))
        return [r[0] for r in cur.fetchall()]

# ---------------- Bad Words ----------------
def load_bad_words():
    if not os.path.exists(BAD_WORDS_FILE):
        with open(BAD_WORDS_FILE, "w") as f:
            json.dump({}, f)
    with open(BAD_WORDS_FILE, "r") as f:
        return json.load(f)

def save_bad_words(data):
    with open(BAD_WORDS_FILE, "w") as f:
        json.dump(data, f, indent=2)

bad_words_per_guild = load_bad_words()

def get_guild_bad_words(guild_id):
    return set(bad_words_per_guild.get(str(guild_id), []))

# ---------------- Logging ----------------
async def log_action(guild, action, member, moderator=None, reason=None):
    channel = discord.utils.get(guild.text_channels, name="mod-log")
    if not channel:
        return
    embed = Embed(
        title=f"Moderation Action: {action}",
        color=discord.Color.red() if action=="Ban" else discord.Color.orange() if action=="Kick" else discord.Color.yellow(),
        timestamp=datetime.now(timezone.utc)
    )
    embed.add_field(name="Member", value=member.mention, inline=True)
    if moderator:
        embed.add_field(name="Moderator", value=moderator.mention, inline=True)
    if reason:
        embed.add_field(name="Reason", value=reason, inline=False)
    await channel.send(embed=embed)

async def send_warning(channel, member, count):
    embed = Embed(
        title="⚠ Warning",
        description=f"{member.mention} has received warning {count}/3",
        color=discord.Color.yellow(),
        timestamp=datetime.now(timezone.utc)
    )
    await channel.send(embed=embed)

# ---------------- Events ----------------
@bot.event
async def on_ready():
    print(f"{bot.user} is online!")
    try:
        synced = await bot.tree.sync()
        print(f"Synced {len(synced)} slash commands")
    except Exception as e:
        print(e)

@bot.event
async def on_message(message):
    if message.author.bot or message.guild is None:
        return

    if message.author.guild_permissions.administrator:
        return

    violated = False
    words_to_check = profanity.union(get_guild_bad_words(message.guild.id))
    for term in words_to_check:
        if term.lower() in message.content.lower():
            violated = True
            break
    if link_regex.search(message.content):
        violated = True

    if violated:
        try:
            await message.delete()
        except:
            pass
        num_warnings = increase_and_get_warnings(message.author.id, message.guild.id)
        await send_warning(message.channel, message.author, num_warnings)
        await log_action(message.guild, "Auto Warning", message.author)

        if num_warnings >= 3:
            until = datetime.now(timezone.utc) + timedelta(hours=1)
            try:
                await message.author.timeout(until, reason="3 warnings - rule violation")
                reset_warnings(message.author.id, message.guild.id)
                await log_action(message.guild, "Timeout", message.author, reason="3 warnings - rule violation")
            except discord.Forbidden:
                await message.channel.send("I don't have permission to timeout this user.")

@bot.event
async def on_member_join(member):
    guild_id = member.guild.id
    channel_id = get_join_channel(guild_id)
    channel = member.guild.get_channel(channel_id) if channel_id else member.guild.system_channel
    join_msg = get_join_message(guild_id)
    if channel and join_msg:
        message_to_send = join_msg.replace("{user}", member.mention).replace("{server}", member.guild.name)
        await channel.send(message_to_send)
    role_ids = get_auto_roles(guild_id)
    for r_id in role_ids.copy():
        role = member.guild.get_role(r_id)
        if role:
            try:
                await member.add_roles(role)
            except:
                pass
        else:
            remove_auto_role_db(guild_id, r_id)

# ---------------- Help View ----------------
class HelpView(View):
    def __init__(self):
        super().__init__(timeout=None)
        self.add_item(Button(label="🛡 Moderation", style=discord.ButtonStyle.danger, custom_id="help_moderation"))
        self.add_item(Button(label="⚠ Warnings", style=discord.ButtonStyle.primary, custom_id="help_warnings"))
        self.add_item(Button(label="🔧 Utility", style=discord.ButtonStyle.secondary, custom_id="help_utility"))
        self.add_item(Button(label="👋 Join Settings", style=discord.ButtonStyle.success, custom_id="help_join"))
        self.add_item(Button(label="🚫 Bad Words", style=discord.ButtonStyle.danger, custom_id="help_badwords"))

embeds = {
    "Moderation": Embed(title="🛡 Moderation Commands", description="""
/kick <member> <reason> - Kick a member
/ban <member> <reason> - Ban a member
/unban <user_id> - Unban a user
/purge <amount> - Delete messages
""", color=discord.Color.red()),
    "Warnings": Embed(title="⚠ Warnings Commands", description="""
/warn <member> <reason> - Warn a member
/removewarn <member> <amount> - Remove warnings
/warningshow <member> - Show warnings
""", color=discord.Color.blurple()),
    "Utility": Embed(title="🔧 Utility Commands", description="""
/userinfo <member> - Show info about a user
/serverinfo - Show server info
/roleinfo <role> - Show role info
/avatar <member> - Show avatar
/ping - Check bot latency
""", color=discord.Color.greyple()),
    "Join Settings": Embed(title="👋 Join Settings", description="""
/setjoinmsg <message> - Set join message
/removejoinmsg - Remove join message
/setjoinchannel <channel> - Set join channel
/addautorole <role> - Add auto role
/removeautorole <role> - Remove auto role
/listautoroles - List auto roles
""", color=discord.Color.green()),
    "Bad Words": Embed(title="🚫 Bad Words Commands", description="""
/addbadword <word> - Add a word to filter
/removebadword <word> - Remove a word from filter
""", color=discord.Color.red())
}

# ---------------- Button Interaction ----------------
@bot.event
async def on_interaction(interaction: discord.Interaction):
    if interaction.type != discord.InteractionType.component:
        return
    cid = interaction.data.get("custom_id")
    mapping = {
        "help_moderation": "Moderation",
        "help_warnings": "Warnings",
        "help_utility": "Utility",
        "help_join": "Join Settings",
        "help_badwords": "Bad Words"
    }
    if cid in mapping:
        await interaction.response.edit_message(embed=embeds[mapping[cid]], view=HelpView())

# ---------------- Slash Commands ----------------

# Moderation
@tree.command(name="kick", description="Kick a member")
@app_commands.checks.has_permissions(kick_members=True)
async def kick(interaction: discord.Interaction, member: discord.Member, reason: str = "No reason provided"):
    if member.guild_permissions.administrator:
        return await interaction.response.send_message("Cannot kick an admin.", ephemeral=True)
    try:
        await member.kick(reason=reason)
        await interaction.response.send_message(f"{member.mention} kicked. Reason: {reason}")
        await log_action(interaction.guild, "Kick", member, moderator=interaction.user, reason=reason)
    except discord.Forbidden:
        await interaction.response.send_message("I cannot kick this member.", ephemeral=True)

@tree.command(name="ban", description="Ban a member")
@app_commands.checks.has_permissions(ban_members=True)
async def ban(interaction: discord.Interaction, member: discord.Member, reason: str = "No reason provided"):
    if member.guild_permissions.administrator:
        return await interaction.response.send_message("Cannot ban an admin.", ephemeral=True)
    try:
        await member.ban(reason=reason)
        await interaction.response.send_message(f"{member.mention} banned. Reason: {reason}")
        await log_action(interaction.guild, "Ban", member, moderator=interaction.user, reason=reason)
    except discord.Forbidden:
        await interaction.response.send_message("I cannot ban this member.", ephemeral=True)

@tree.command(name="unban", description="Unban a user by ID")
@app_commands.checks.has_permissions(ban_members=True)
async def unban(interaction: discord.Interaction, user_id: int):
    try:
        user = await bot.fetch_user(user_id)
    except:
        return await interaction.response.send_message("Invalid user ID.", ephemeral=True)
    banned_users = [ban async for ban in interaction.guild.bans()]
    for ban_entry in banned_users:
        if ban_entry.user.id == user.id:
            await interaction.guild.unban(user)
            await interaction.response.send_message(f"Unbanned {user}.")
            await log_action(interaction.guild, "Unban", user, moderator=interaction.user)
            return
    await interaction.response.send_message(f"User {user} is not banned.", ephemeral=True)

@tree.command(name="purge", description="Delete messages")
@app_commands.checks.has_permissions(manage_messages=True)
async def purge(interaction: discord.Interaction, amount: int):
    if amount < 1:
        return await interaction.response.send_message("You must delete at least 1 message.", ephemeral=True)
    deleted = await interaction.channel.purge(limit=amount)
    await interaction.response.send_message(f"Deleted {len(deleted)} message(s).", ephemeral=True)

# Warnings
@tree.command(name="warn", description="Warn a member")
@app_commands.checks.has_permissions(moderate_members=True)
async def warn(interaction: discord.Interaction, member: discord.Member, reason: str = "No reason provided"):
    if member.guild_permissions.administrator:
        return await interaction.response.send_message("Cannot warn an admin.", ephemeral=True)
    num_warnings = increase_and_get_warnings(member.id, interaction.guild.id)
    await send_warning(interaction.channel, member, num_warnings)
    await log_action(interaction.guild, "Manual Warning", member, moderator=interaction.user, reason=reason)
    if num_warnings >= 3:
        until = datetime.now(timezone.utc) + timedelta(hours=1)
        try:
            await member.timeout(until, reason="3 warnings - rule violation")
            reset_warnings(member.id, interaction.guild.id)
            await log_action(interaction.guild, "Timeout", member, moderator=interaction.user, reason="3 warnings - rule violation")
        except discord.Forbidden:
            await interaction.channel.send("I don't have permission to timeout this user.")
    await interaction.response.send_message(f"{member.mention} warned! Current warnings: {num_warnings}")

@tree.command(name="removewarn", description="Remove warnings from a member")
@app_commands.checks.has_permissions(moderate_members=True)
async def removewarn(interaction: discord.Interaction, member: discord.Member, amount: int = 1):
    current = get_warnings(member.id, interaction.guild.id)
    new_count = max(current - amount, 0)
    with sqlite3.connect(DB_PATH) as conn:
        cur = conn.cursor()
        if new_count == 0:
            cur.execute("DELETE FROM users_per_guild WHERE user_id=? AND guild_id=?", (member.id, interaction.guild.id))
        else:
            cur.execute("UPDATE users_per_guild SET warning_count=? WHERE user_id=? AND guild_id=?", (new_count, member.id, interaction.guild.id))
        conn.commit()
    await interaction.response.send_message(f"{amount} warning(s) removed from {member.mention}. New total: {new_count}")
    await log_action(interaction.guild, "Manual Warning Removal", member, moderator=interaction.user)

@tree.command(name="warningshow", description="Show warnings of a member")
async def warningshow(interaction: discord.Interaction, member: discord.Member = None):
    member = member or interaction.user
    count = get_warnings(member.id, interaction.guild.id)
    await interaction.response.send_message(f"{member.mention} has {count} warning(s).")

# Bad Words
@tree.command(name="addbadword", description="Add a word to filter")
@app_commands.checks.has_permissions(administrator=True)
async def addbadword(interaction: discord.Interaction, word: str):
    guild_id = str(interaction.guild.id)
    words = set(bad_words_per_guild.get(guild_id, []))
    words.add(word.lower())
    bad_words_per_guild[guild_id] = list(words)
    save_bad_words(bad_words_per_guild)
    await interaction.response.send_message(f"Added '{word}' to server filter.")

@tree.command(name="removebadword", description="Remove a word from filter")
@app_commands.checks.has_permissions(administrator=True)
async def removebadword(interaction: discord.Interaction, word: str):
    guild_id = str(interaction.guild.id)
    words = set(bad_words_per_guild.get(guild_id, []))
    if word.lower() in words:
        words.remove(word.lower())
        bad_words_per_guild[guild_id] = list(words)
        save_bad_words(bad_words_per_guild)
        await interaction.response.send_message(f"Removed '{word}' from server filter.")
    else:
        await interaction.response.send_message(f"'{word}' was not in the filter.")

# Utility
@tree.command(name="ping", description="Check bot latency")
async def ping(interaction: discord.Interaction):
    latency = round(bot.latency * 1000)
    await interaction.response.send_message(f"Pong! 🏓 Latency: {latency}ms")

@tree.command(name="userinfo", description="Show info about a user")
@app_commands.checks.has_permissions(administrator=True)
async def userinfo(interaction: discord.Interaction, member: discord.Member = None):
    member = member or interaction.user
    embed = Embed(
        title=f"User Info: {member}",
        color=discord.Color.green(),
        timestamp=datetime.now(timezone.utc)
    )
    embed.set_thumbnail(url=member.avatar.url if member.avatar else member.default_avatar.url)
    embed.add_field(name="ID", value=member.id)
    embed.add_field(name="Top Role", value=member.top_role.mention)
    embed.add_field(name="Joined Server", value=member.joined_at.strftime("%Y-%m-%d %H:%M:%S UTC"))
    embed.add_field(name="Account Created", value=member.created_at.strftime("%Y-%m-%d %H:%M:%S UTC"))
    embed.add_field(name="Warnings", value=get_warnings(member.id, interaction.guild.id))
    await interaction.response.send_message(embed=embed)

# Join Messages & Auto Roles
@tree.command(name="setjoinmsg", description="Set custom join message")
@app_commands.checks.has_permissions(administrator=True)
async def setjoinmsg(interaction: discord.Interaction, message: str):
    set_join_message(interaction.guild.id, message)
    await interaction.response.send_message("✅ Custom join message set!")

@tree.command(name="removejoinmsg", description="Remove custom join message")
@app_commands.checks.has_permissions(administrator=True)
async def removejoinmsg(interaction: discord.Interaction):
    remove_join_message(interaction.guild.id)
    await interaction.response.send_message("✅ Custom join message removed!")

@tree.command(name="setjoinchannel", description="Set join message channel")
@app_commands.checks.has_permissions(administrator=True)
async def setjoinchannel(interaction: discord.Interaction, channel: discord.TextChannel):
    set_join_channel(interaction.guild.id, channel.id)
    await interaction.response.send_message(f"✅ Join messages will be sent in {channel.mention}")

@tree.command(name="addautorole", description="Add auto role for new members")
@app_commands.checks.has_permissions(administrator=True)
async def addautorole(interaction: discord.Interaction, role: discord.Role):
    add_auto_role(interaction.guild.id, role.id)
    await interaction.response.send_message(f"✅ {role.mention} will now be automatically assigned to new members.")

@tree.command(name="removeautorole", description="Remove auto role")
@app_commands.checks.has_permissions(administrator=True)
async def removeautorole(interaction: discord.Interaction, role: discord.Role):
    remove_auto_role_db(interaction.guild.id, role.id)
    await interaction.response.send_message(f"✅ {role.mention} will no longer be automatically assigned.")

@tree.command(name="listautoroles", description="List all auto roles")
@app_commands.checks.has_permissions(administrator=True)
async def listautoroles(interaction: discord.Interaction):
    roles = get_auto_roles(interaction.guild.id)
    if roles:
        role_mentions = [interaction.guild.get_role(r).mention for r in roles if interaction.guild.get_role(r)]
        await interaction.response.send_message("Auto Roles: " + ", ".join(role_mentions))
    else:
        await interaction.response.send_message("No auto roles set.")

# ---------------- Run ----------------
bot.run(TOKEN)

