import discord
from discord.ext import commands
import os
import sqlite3
import re
import logging
from datetime import datetime, timedelta
from flask import Flask
from dotenv import load_dotenv

# ---------------- Load .env ----------------
load_dotenv()
TOKEN = os.getenv("TOKEN")
PREFIX = "!"

# ---------------- Logging ----------------
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("discord_bot")

# ---------------- Bot Setup ----------------
intents = discord.Intents.all()
bot = commands.Bot(command_prefix=PREFIX, intents=intents)

# ---------------- Keep Alive Server ----------------
app = Flask('')

@app.route('/')
def home():
    return "Bot is alive!"

def keep_alive():
    app.run(host='0.0.0.0', port=8080)

# ---------------- Database Setup ----------------
conn = sqlite3.connect('bot.db')
c = conn.cursor()

# Warnings Table
c.execute('''CREATE TABLE IF NOT EXISTS warns (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    guild_id INTEGER,
    user_id INTEGER,
    mod_id INTEGER,
    reason TEXT,
    timestamp TEXT
)''')

# Word Filters Table
c.execute('''CREATE TABLE IF NOT EXISTS filters (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    guild_id INTEGER,
    word TEXT
)''')

# Config Table
c.execute('''CREATE TABLE IF NOT EXISTS config (
    guild_id INTEGER PRIMARY KEY,
    welcome_channel INTEGER,
    rules_channel INTEGER,
    roles_channel INTEGER,
    intro_channel INTEGER,
    modlog_channel INTEGER
)''')
conn.commit()

# ---------------- Helper Functions ----------------
def add_warn_db(guild_id, user_id, mod_id, reason):
    c.execute("INSERT INTO warns (guild_id,user_id,mod_id,reason,timestamp) VALUES (?,?,?,?,?)",
              (guild_id, user_id, mod_id, reason, datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")))
    conn.commit()

def get_warns_db(guild_id, user_id):
    c.execute("SELECT * FROM warns WHERE guild_id=? AND user_id=? ORDER BY id DESC", (guild_id, user_id))
    return c.fetchall()

def list_filters_db(guild_id):
    c.execute("SELECT word FROM filters WHERE guild_id=?", (guild_id,))
    return [r[0] for r in c.fetchall()]

def is_moderator(member: discord.Member):
    return member.guild_permissions.kick_members or member.guild_permissions.ban_members

def safe_dm(member: discord.Member, content):
    try:
        return member.send(content)
    except Exception:
        return None

def post_modlog(guild: discord.Guild, content: str):
    c.execute("SELECT modlog_channel FROM config WHERE guild_id=?", (guild.id,))
    row = c.fetchone()
    if row and row[0]:
        ch = guild.get_channel(row[0])
        if ch:
            try:
                return ch.send(content)
            except Exception:
                pass

            # ---------------- Events ----------------
@bot.event
async def on_ready():
    logger.info(f"Bot ready as {bot.user} (ID: {bot.user.id})")
    try:
        await bot.change_presence(activity=discord.Game(name=f"{PREFIX}help | Moderation Bot"))
    except Exception:
        pass

@bot.event
async def on_member_join(member: discord.Member):
    c.execute("SELECT welcome_channel, rules_channel, roles_channel, intro_channel FROM config WHERE guild_id=?", (member.guild.id,))
    cfg = c.fetchone()
    if not cfg or not cfg[0]:
        return
    welcome_channel_id, rules_channel, roles_channel, intro_channel = cfg
    ch = member.guild.get_channel(welcome_channel_id)
    if not ch:
        return
    embed = discord.Embed(
        title="🎉 Welcome to Royals Empire 🍻",
        description=f"Hey {member.mention} 👑\nYou’ve just stepped into the kingdom of vibes, loyalty, and legends.\nWe're hyped to have you with us!",
        color=discord.Color.gold()
    )
    fields = []
    if rules_channel:
        fields.append(f"🔹 Read the rules in <#{rules_channel}>")
    if roles_channel:
        fields.append(f"🔹 Get your roles from <#{roles_channel}>")
    if intro_channel:
        fields.append(f"🔹 Say hi in <#{intro_channel}>")
    if fields:
        embed.add_field(name="Make sure to:", value="\n".join(fields), inline=False)
    embed.set_footer(text=f"Member ID: {member.id}")
    try:
        await ch.send(embed=embed)
    except Exception:
        logger.exception("Failed to send welcome message")

@bot.event
async def on_message(message: discord.Message):
    if message.author.bot or not message.guild:
        return
    # Moderators exempt
    if is_moderator(message.author):
        await bot.process_commands(message)
        return
    # Link filter
    if re.search(r"(https?://\S+|www\.\S+)", message.content, re.IGNORECASE):
        try:
            await message.delete()
        except Exception:
            pass
        await handle_auto_warn(message.guild, message.author, "Posted a link")
        try:
            await message.channel.send(f"{message.author.mention}, posting links is not allowed. Warning issued.", delete_after=6)
        except Exception:
            pass
        return
    # Word filter
    bad_words = list_filters_db(message.guild.id)
    msg_lower = message.content.lower()
    for w in bad_words:
        if re.search(rf"\b{re.escape(w)}\b", msg_lower):
            try:
                await message.delete()
            except Exception:
                pass
            await handle_auto_warn(message.guild, message.author, f"Used banned word: {w}")
            try:
                await message.channel.send(f"{message.author.mention}, that word is not allowed. Warning recorded.", delete_after=6)
            except Exception:
                pass
            return
    await bot.process_commands(message)

# ---------------- Auto-Warn Handler ----------------
async def handle_auto_warn(guild: discord.Guild, member: discord.Member, reason: str):
    add_warn_db(guild.id, member.id, 0, reason)  # mod_id=0 for auto
    rows = get_warns_db(guild.id, member.id)
    count = len(rows)
    await safe_dm(member, f"You received an automatic warning in *{guild.name}*.\nReason: {reason}\nTotal warns: {count}")
    c.execute("SELECT modlog_channel FROM config WHERE guild_id=?", (guild.id,))
    row = c.fetchone()
    if row and row[0]:
        ch = guild.get_channel(row[0])
        if ch:
            try:
                await ch.send(f"AutoWarn: {member} — {reason} (Total warns: {count})")
            except Exception:
                pass
    if count >= 3:
        try:
            until = datetime.utcnow() + timedelta(hours=1)
            await member.edit(timeout=until)
            if row and row[0] and ch:
                await ch.send(f"{member} was timed out for 1 hour after reaching 3 warnings.")
            await safe_dm(member, f"You have been timed out for 1 hour in *{guild.name}* after reaching 3 warnings.")
        except Exception:
            logger.exception("Failed to timeout member after 3 warns.")

# ---------------- Helper for Embed Formatting ----------------
def format_warns_for_embed(rows):
    text = ""
    for r in rows[:10]:
        wid, guildid, mod_id, reason, ts = r
        mod_display = "AutoFilter" if mod_id == 0 else f"<@{mod_id}>"
        text += f"ID {wid} • By {mod_display} • {reason} • {ts}\n"
    return text or "No warnings."

# ---------------- COMMANDS ----------------

# Help
@bot.command(name="help")
async def help_command(ctx: commands.Context):
    embed = discord.Embed(title="Bot Help", description="Here are the available commands:")
    embed.add_field(name="Moderation", value=(
        f"!kick <member> [reason]\n"
        f"!ban <member> [reason]\n"
        f"!unban <user_id>\n"
        f"!warn <member> [reason]\n"
        f"!warnings <member>\n"
        f"!timeout <member> <minutes>\n"
        f"!remove_timeout <member>\n"
    ), inline=False)
    embed.add_field(name="Info", value=(
        f"!avatar <member>\n"
        f"!serverinfo\n"
        f"!memberinfo <member> (admins only)\n"
        f"!roleinfo <role> (admins only)\n"
    ), inline=False)
    await ctx.send(embed=embed)

# Kick
@bot.command(name="kick")
@commands.has_permissions(kick_members=True)
async def kick(ctx: commands.Context, member: discord.Member, *, reason: str = "No reason provided"):
    try:
        await safe_dm(member, f"You were kicked from *{ctx.guild.name}*.\nReason: {reason}\nModerator: {ctx.author}")
    except:
        pass
    try:
        await member.kick(reason=reason)
        await ctx.send(f"{member} was kicked. Reason: {reason}")
        await post_modlog(ctx.guild, f"{ctx.author} kicked {member} — {reason}")
    except Exception as e:
        await ctx.send(f"Failed to kick: {e}")

# Ban
@bot.command(name="ban")
@commands.has_permissions(ban_members=True)
async def ban(ctx: commands.Context, member: discord.Member, *, reason: str = "No reason provided"):
    try:
        await safe_dm(member, f"You were banned from *{ctx.guild.name}*.\nReason: {reason}\nModerator: {ctx.author}")
    except:
        pass
    try:
        await member.ban(reason=reason)
        await ctx.send(f"{member} was banned. Reason: {reason}")
        await post_modlog(ctx.guild, f"{ctx.author} banned {member} — {reason}")
    except Exception as e:
        await ctx.send(f"Failed to ban: {e}")

# Unban
@bot.command(name="unban")
@commands.has_permissions(ban_members=True)
async def unban(ctx: commands.Context, user_id: int):
    try:
        user = await bot.fetch_user(user_id)
        await ctx.guild.unban(user)
        await ctx.send(f"Unbanned {user}.")
        await post_modlog(ctx.guild, f"{ctx.author} unbanned {user}.")
    except Exception as e:
        await ctx.send(f"Failed to unban: {e}")

# Warn
@bot.command(name="warn")
@commands.has_permissions(manage_messages=True)
async def warn(ctx: commands.Context, member: discord.Member, *, reason: str = "Rule break"):
    add_warn_db(ctx.guild.id, member.id, ctx.author.id, reason)
    rows = get_warns_db(ctx.guild.id, member.id)
    count = len(rows)
    await ctx.send(f"{member.mention} has been warned. Total warns: {count}. Reason: {reason}")
    await safe_dm(member, f"You received a warning in *{ctx.guild.name}*.\nReason: {reason}\nModerator: {ctx.author}\nTotal warns: {count}")
    await post_modlog(ctx.guild, f"{ctx.author} warned {member} — {reason} (Total warns: {count})")
    if count >= 3:
        try:
            until = datetime.utcnow() + timedelta(hours=1)
            await member.edit(timeout=until)
            await ctx.send(f"{member.mention} has been timed out for 1 hour (3 warnings).")
            await post_modlog(ctx.guild, f"{member} timed out for 1 hour after 3 warnings.")
            await safe_dm(member, f"You have been timed out in *{ctx.guild.name}* for 1 hour after 3 warnings.")
        except Exception:
            logger.exception("Failed to timeout member on 3 warns")

# Warnings
@bot.command(name="warnings")
async def warnings(ctx: commands.Context, member: discord.Member = None):
    target = member or ctx.author
    if target != ctx.author and not is_moderator(ctx.author):
        await ctx.send("You don't have permission to view other members' warnings.")
        return
    rows = get_warns_db(ctx.guild.id, target.id)
    embed = discord.Embed(title=f"Warnings for {target}", description=f"Total: {len(rows)}")
    embed.add_field(name="Recent warns (latest first)", value=format_warns_for_embed(rows), inline=False)
    await ctx.send(embed=embed)

# Timeout
@bot.command(name="timeout")
@commands.has_permissions(moderate_members=True)
async def timeout(ctx: commands.Context, member: discord.Member, minutes: int = 60):
    try:
        until = datetime.utcnow() + timedelta(minutes=minutes)
        await member.edit(timeout=until)
        await ctx.send(f"{member.mention} timed out for {minutes} minutes.")
        await post_modlog(ctx.guild, f"{ctx.author} timed out {member} for {minutes} minutes.")
        await safe_dm(member, f"You were timed out in *{ctx.guild.name}* for {minutes} minutes.\nModerator: {ctx.author}")
    except Exception as e:
        await ctx.send(f"Failed to timeout: {e}")

# Remove Timeout
@bot.command(name="remove_timeout")
@commands.has_permissions(moderate_members=True)
async def remove_timeout(ctx: commands.Context, member: discord.Member):
    try:
        await member.edit(timeout=None)
        await ctx.send(f"Timeout removed for {member.mention}.")
        await post_modlog(ctx.guild, f"{ctx.author} removed timeout for {member}.")
        await safe_dm(member, f"Your timeout has been removed in *{ctx.guild.name}*.\nModerator: {ctx.author}")
    except Exception as e:
        await ctx.send(f"Failed to remove timeout: {e}")

# ---------------- Error Handling ----------------
@bot.event
async def on_command_error(ctx, error):
    if isinstance(error, commands.MissingPermissions):
        await ctx.send("You don't have permission to run this command.")
    elif isinstance(error, commands.MissingRequiredArgument):
        await ctx.send("Missing required argument.")
    elif isinstance(error, commands.CommandNotFound):
        await ctx.send("Command not found.")
    else:
        await ctx.send(f"Error: {error}")
        logger.exception("Command error:")

@bot.event
async def on_error(event_method, *args, **kwargs):
    logger.exception(f"Unhandled error in {event_method}:")

# ---------------- BOT RUN ----------------
if __name__ == "_main_":
    keep_alive()  # start web server for Render
    bot.run(TOKEN)