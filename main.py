import os
import discord
from discord.ext import commands
from dotenv import load_dotenv
import sqlite3
from datetime import datetime, timedelta, timezone
import re
import json

# ---------------- Setup ----------------
load_dotenv()
TOKEN = os.getenv("DISCORD_TOKEN")
if not TOKEN:
    raise SystemExit("DISCORD_TOKEN not found in .env")

PREFIX = "!"
DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "bot_data.db")
BAD_WORDS_FILE = "server_bad_words.json"

# ---------------- Profanity & Links ----------------
profanity = {"poopoo"}
link_regex = re.compile(r"https?://\S+|www\.\S+", re.IGNORECASE)

# ---------------- Bot ----------------
intents = discord.Intents.all()
bot = commands.Bot(command_prefix=PREFIX, intents=intents, help_command=None)

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

# ---------------- Logging & Warnings ----------------
async def log_action(guild, action, member, moderator=None, reason=None):
    channel = discord.utils.get(guild.text_channels, name="mod-log")
    if not channel:
        return
    embed = discord.Embed(
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
    embed = discord.Embed(
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

@bot.event
async def on_message(message):
    if message.author.bot or message.guild is None:
        return
    await bot.process_commands(message)

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

    

# ---------------- Member Join ----------------
@bot.event
async def on_member_join(member):
    guild_id = member.guild.id

    # Get join channel
    channel_id = get_join_channel(guild_id)
    channel = member.guild.get_channel(channel_id) if channel_id else member.guild.system_channel

    # Get join message
    join_msg = get_join_message(guild_id)
    if channel and join_msg:
        # Replace placeholders
        message_to_send = join_msg.replace("{user}", member.mention).replace("{server}", member.guild.name)
        await channel.send(message_to_send)


    # Auto Roles
    role_ids = get_auto_roles(guild_id)
    for r_id in role_ids.copy():
        role = member.guild.get_role(r_id)
        if role:
            try:
                await member.add_roles(role)
            except:
                pass
        else:  # role deleted
            remove_auto_role_db(guild_id, r_id)

# ---------------- Commands ----------------

## Moderation
@bot.command()
@commands.has_permissions(kick_members=True)
async def kick(ctx, member: discord.Member, *, reason="No reason provided"):
    if member.guild_permissions.administrator:
        return await ctx.send("Cannot kick an admin.")
    try:
        await member.kick(reason=reason)
        await ctx.send(f"{member.mention} kicked. Reason: {reason}")
        await log_action(ctx.guild, "Kick", member, moderator=ctx.author, reason=reason)
    except discord.Forbidden:
        await ctx.send("I cannot kick this member.")

@bot.command()
@commands.has_permissions(ban_members=True)
async def ban(ctx, member: discord.Member, *, reason="No reason provided"):
    if member.guild_permissions.administrator:
        return await ctx.send("Cannot ban an admin.")
    try:
        await member.ban(reason=reason)
        await ctx.send(f"{member.mention} banned. Reason: {reason}")
        await log_action(ctx.guild, "Ban", member, moderator=ctx.author, reason=reason)
    except discord.Forbidden:
        await ctx.send("I cannot ban this member.")

@bot.command()
@commands.has_permissions(ban_members=True)
async def unban(ctx, user_id: int):
    try:
        user = await bot.fetch_user(user_id)
    except:
        return await ctx.send("Invalid user ID.")
    banned_users = [ban async for ban in ctx.guild.bans()]
    for ban_entry in banned_users:
        if ban_entry.user.id == user.id:
            await ctx.guild.unban(user)
            await ctx.send(f"Unbanned {user}.")
            await log_action(ctx.guild, "Unban", user, moderator=ctx.author)
            return
    await ctx.send(f"User {user} is not banned.")

@bot.command()
@commands.has_permissions(manage_messages=True)
async def purge(ctx, amount: int):
    if amount < 1:
        return await ctx.send("You must delete at least 1 message.")
    deleted = await ctx.channel.purge(limit=amount)
    await ctx.send(f"Deleted {len(deleted)} message(s).", delete_after=5)

## Warnings
@bot.command()
@commands.has_permissions(moderate_members=True)
async def warn(ctx, member: discord.Member, *, reason="No reason provided"):
    if member.guild_permissions.administrator:
        return await ctx.send("Cannot warn an admin.")
    num_warnings = increase_and_get_warnings(member.id, ctx.guild.id)
    await send_warning(ctx.channel, member, num_warnings)
    await log_action(ctx.guild, "Manual Warning", member, moderator=ctx.author, reason=reason)
    if num_warnings >= 3:
        until = datetime.now(timezone.utc) + timedelta(hours=1)
        try:
            await member.timeout(until, reason="3 warnings - rule violation")
            reset_warnings(member.id, ctx.guild.id)
            await log_action(ctx.guild, "Timeout", member, moderator=ctx.author, reason="3 warnings - rule violation")
        except discord.Forbidden:
            await ctx.send("I don't have permission to timeout this user.")
    await ctx.send(f"{member.mention} warned! Current warnings: {num_warnings}")

@bot.command()
@commands.has_permissions(moderate_members=True)
async def removewarn(ctx, member: discord.Member, amount: int = 1):
    current = get_warnings(member.id, ctx.guild.id)
    new_count = max(current - amount, 0)
    with sqlite3.connect(DB_PATH) as conn:
        cur = conn.cursor()
        if new_count == 0:
            cur.execute("DELETE FROM users_per_guild WHERE user_id=? AND guild_id=?", (member.id, ctx.guild.id))
        else:
            cur.execute("UPDATE users_per_guild SET warning_count=? WHERE user_id=? AND guild_id=?", (new_count, member.id, ctx.guild.id))
        conn.commit()
    await ctx.send(f"{amount} warning(s) removed from {member.mention}. New total: {new_count}")
    await log_action(ctx.guild, "Manual Warning Removal", member, moderator=ctx.author)

@bot.command()
async def warningshow(ctx, member: discord.Member = None):
    member = member or ctx.author
    count = get_warnings(member.id, ctx.guild.id)
    await ctx.send(f"{member.mention} has {count} warning(s).")

## Bad Words
@bot.command()
@commands.has_permissions(administrator=True)
async def addbadword(ctx, word: str):
    guild_id = str(ctx.guild.id)
    words = set(bad_words_per_guild.get(guild_id, []))
    words.add(word.lower())
    bad_words_per_guild[guild_id] = list(words)
    save_bad_words(bad_words_per_guild)
    await ctx.send(f"Added '{word}' to server filter.")

@bot.command()
@commands.has_permissions(administrator=True)
async def removebadword(ctx, word: str):
    guild_id = str(ctx.guild.id)
    words = set(bad_words_per_guild.get(guild_id, []))
    if word.lower() in words:
        words.remove(word.lower())
        bad_words_per_guild[guild_id] = list(words)
        save_bad_words(bad_words_per_guild)
        await ctx.send(f"Removed '{word}' from server filter.")
    else:
        await ctx.send(f"'{word}' was not in the filter.")

## Utility
@bot.command()
async def ping(ctx):
    latency = round(bot.latency * 1000)
    await ctx.send(f"Pong! 🏓 Latency: {latency}ms")

@bot.command()
@commands.has_permissions(administrator=True)
async def userinfo(ctx, member: discord.Member = None):
    member = member or ctx.author
    embed = discord.Embed(
        title=f"User Info: {member}",
        color=discord.Color.green(),
        timestamp=datetime.now(timezone.utc)
    )
    embed.set_thumbnail(url=member.avatar.url if member.avatar else member.default_avatar.url)
    embed.add_field(name="ID", value=member.id)
    embed.add_field(name="Top Role", value=member.top_role.mention)
    embed.add_field(name="Joined Server", value=member.joined_at.strftime("%Y-%m-%d %H:%M:%S UTC"))
    embed.add_field(name="Account Created", value=member.created_at.strftime("%Y-%m-%d %H:%M:%S UTC"))
    embed.add_field(name="Warnings", value=get_warnings(member.id, ctx.guild.id))
    await ctx.send(embed=embed)

@bot.command()
@commands.has_permissions(administrator=True)
async def setjoinmsg(ctx, *, message):
    # Remove any leading !setjoinmsg from the saved message
    if message.lower().startswith(f"{PREFIX}setjoinmsg"):
        message = message[len(f"{PREFIX}setjoinmsg"):].strip()
    set_join_message(ctx.guild.id, message)
    await ctx.send("✅ Custom join message set!")


@bot.command()
@commands.has_permissions(administrator=True)
async def removejoinmsg(ctx):
    remove_join_message(ctx.guild.id)
    await ctx.send("✅ Custom join message removed!")

@bot.command()
@commands.has_permissions(administrator=True)
async def setjoinchannel(ctx, channel: discord.TextChannel):
    set_join_channel(ctx.guild.id, channel.id)
    await ctx.send(f"✅ Join messages will be sent in {channel.mention}")

@bot.command()
@commands.has_permissions(administrator=True)
async def addautorole(ctx, role: discord.Role):
    add_auto_role(ctx.guild.id, role.id)
    await ctx.send(f"✅ {role.mention} will now be automatically assigned to new members.")

@bot.command()
@commands.has_permissions(administrator=True)
async def removeautorole(ctx, role: discord.Role):
    remove_auto_role_db(ctx.guild.id, role.id)
    await ctx.send(f"✅ {role.mention} will no longer be automatically assigned.")

@bot.command()
@commands.has_permissions(administrator=True)
async def listautoroles(ctx):
    roles = get_auto_roles(ctx.guild.id)
    if roles:
        role_mentions = [ctx.guild.get_role(r).mention for r in roles if ctx.guild.get_role(r)]
        await ctx.send("Auto Roles: " + ", ".join(role_mentions))
    else:
        await ctx.send("No auto roles set.")

from discord.ext import commands
import discord
from discord import Embed
from discord.ui import View, Button

# ---------- Help View ----------
class HelpView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)
        # Add buttons with emojis for categories
        self.add_item(Button(label="🛡 Moderation", style=discord.ButtonStyle.danger, custom_id="help_moderation"))
        self.add_item(Button(label="⚠ Warnings", style=discord.ButtonStyle.primary, custom_id="help_warnings"))
        self.add_item(Button(label="🔧 Utility", style=discord.ButtonStyle.secondary, custom_id="help_utility"))
        self.add_item(Button(label="👋 Join Settings", style=discord.ButtonStyle.success, custom_id="help_join"))
        self.add_item(Button(label="🚫 Bad Words", style=discord.ButtonStyle.danger, custom_id="help_badwords"))

# ---------- Help Embeds ----------
embeds = {
    "Moderation": Embed(
        title="🛡 Moderation Commands",
        description="""
**!kick <member> <reason>** - Kick a member  
**!ban <member> <reason>** - Ban a member  
**!unban <user_id>** - Unban a user by ID  
**!purge <amount>** - Delete messages  
""",
        color=discord.Color.red()
    ),
    "Warnings": Embed(
        title="⚠ Warnings Commands",
        description="""
**!warn <member> <reason>** - Warn a member  
**!removewarn <member> <amount>** - Remove warnings  
**!warningshow <member>** - Show warnings  
""",
        color=discord.Color.blurple()
    ),
    "Utility": Embed(
        title="🔧 Utility Commands",
        description="""
**!userinfo <member>** - Show info about a user  
**!serverinfo** - Show server info  
**!roleinfo <role>** - Show role info  
**!avatar <member>** - Show avatar  
**!ping** - Check bot latency  
""",
        color=discord.Color.greyple()
    ),
    "Join Settings": Embed(
        title="👋 Join Settings",
        description="""
**!setjoinmsg <message>** - Set a custom join message  
**!removejoinmsg** - Remove the custom join message  
**!setjoinchannel <channel>** - Set the join message channel  
**!addautorole <role>** - Add role for new members  
**!removeautorole <role>** - Remove auto role  
**!listautoroles** - List all auto roles  
""",
        color=discord.Color.green()
    ),
    "Bad Words": Embed(
        title="🚫 Bad Words Commands",
        description="""
**!addbadword <word>** - Add a word to filter  
**!removebadword <word>** - Remove a word from filter  
""",
        color=discord.Color.red()
    )
}

# ---------- Help Command ----------
@bot.command(name="help")
async def help_command(ctx):
    view = HelpView()
    await ctx.send(
        embed=Embed(
            title="📚 Help Menu",
            description="Select a category below to view commands.",
            color=discord.Color.blurple()
        ),
        view=view
    )

# ---------- Button Interaction ----------
@bot.event
async def on_interaction(interaction: discord.Interaction):
    if interaction.type != discord.InteractionType.component:
        return

    cid = interaction.data.get("custom_id")
    if cid in ["help_moderation", "help_warnings", "help_utility", "help_join", "help_badwords"]:
        category = {
            "help_moderation": "Moderation",
            "help_warnings": "Warnings",
            "help_utility": "Utility",
            "help_join": "Join Settings",
            "help_badwords": "Bad Words"
        }[cid]

        # Send the corresponding embed
        await interaction.response.edit_message(embed=embeds[category], view=HelpView())


# ---------------- Run ----------------
bot.run(TOKEN)
