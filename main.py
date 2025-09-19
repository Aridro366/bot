import discord
from discord import app_commands
from discord.ext import commands
import os
import sqlite3
import re
import logging
from datetime import datetime, timedelta
from flask import Flask
from dotenv import load_dotenv

# ---------- Load .env ----------
load_dotenv()
TOKEN = os.getenv("TOKEN")
PREFIX = "/"  # Not used, just info

# ---------- Logging ----------
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("discord_bot")

# ---------- Bot Setup ----------
intents = discord.Intents.all()
bot = commands.Bot(command_prefix="/", intents=intents)
tree = bot.tree

# ---------- Keep Alive Server ----------
app = Flask('')

@app.route('/')
def home():
    return "Bot is alive!"

def keep_alive():
    app.run(host='0.0.0.0', port=8080)

# ---------- Database Setup ----------
conn = sqlite3.connect('bot.db')
c = conn.cursor()

c.execute('''CREATE TABLE IF NOT EXISTS warns (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    guild_id INTEGER,
    user_id INTEGER,
    mod_id INTEGER,
    reason TEXT,
    timestamp TEXT
)''')

c.execute('''CREATE TABLE IF NOT EXISTS filters (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    guild_id INTEGER,
    word TEXT
)''')

c.execute('''CREATE TABLE IF NOT EXISTS config (
    guild_id INTEGER PRIMARY KEY,
    welcome_channel INTEGER,
    rules_channel INTEGER,
    roles_channel INTEGER,
    intro_channel INTEGER,
    modlog_channel INTEGER
)''')
conn.commit()

# ---------- Helper Functions ----------
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

# ---------- Events ----------
@bot.event
async def on_ready():
    try:
        await tree.sync()  # Sync slash commands
        logger.info("Slash commands synced.")
    except Exception:
        logger.exception("Failed to sync slash commands.")
    logger.info(f"Bot ready as {bot.user} (ID: {bot.user.id})")
    try:
        await bot.change_presence(activity=discord.Game(name="Use /help for commands"))
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
            await message.channel.send(f"{message.author.mention}, posting links is not allowed. This has been recorded as a warning.", delete_after=6)
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

# ---------- Auto-Warn Handler ----------
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

# ---------- Helper for Embed Formatting ----------
def format_warns_for_embed(rows):
    text = ""
    for r in rows[:10]:
        wid, guildid, mod_id, reason, ts = r
        mod_display = "AutoFilter" if mod_id == 0 else f"<@{mod_id}>"
        text += f"ID {wid} • By {mod_display} • {reason} • {ts}\n"
    return text or "No warnings."

# ---------- SLASH COMMANDS ----------
# Kick
@tree.command(name="kick", description="Kick a member")
@app_commands.describe(member="Member to kick", reason="Reason for kick")
async def kick_slash(interaction: discord.Interaction, member: discord.Member, reason: str = "No reason provided"):
    if not interaction.user.guild_permissions.kick_members:
        await interaction.response.send_message("You don't have permission.", ephemeral=True)
        return
    try:
        await safe_dm(member, f"You were kicked from *{interaction.guild.name}*.\nReason: {reason}\nModerator: {interaction.user}")
    except Exception:
        pass
    try:
        await member.kick(reason=reason)
        await interaction.response.send_message(f"{member} was kicked. Reason: {reason}")
        await post_modlog(interaction.guild, f"{interaction.user} kicked {member} — {reason}")
    except Exception as e:
        await interaction.response.send_message(f"Failed to kick: {e}")

# Ban
@tree.command(name="ban", description="Ban a member")
@app_commands.describe(member="Member to ban", reason="Reason for ban")
async def ban_slash(interaction: discord.Interaction, member: discord.Member, reason: str = "No reason provided"):
    if not interaction.user.guild_permissions.ban_members:
        await interaction.response.send_message("You don't have permission.", ephemeral=True)
        return
    try:
        await safe_dm(member, f"You have been banned from *{interaction.guild.name}*.\nReason: {reason}\nModerator: {interaction.user}")
    except Exception:
        pass
    try:
        await member.ban(reason=reason)
        await interaction.response.send_message(f"{member} was banned. Reason: {reason}")
        await post_modlog(interaction.guild, f"{interaction.user} banned {member} — {reason}")
    except Exception as e:
        await interaction.response.send_message(f"Failed to ban: {e}")

# Warn
@tree.command(name="warn", description="Warn a member")
@app_commands.describe(member="Member to warn", reason="Reason for warning")
async def warn_slash(interaction: discord.Interaction, member: discord.Member, reason: str = "Rule break"):
    if not interaction.user.guild_permissions.manage_messages:
        await interaction.response.send_message("You don't have permission.", ephemeral=True)
        return
    add_warn_db(interaction.guild.id, member.id, interaction.user.id, reason)
    rows = get_warns_db(interaction.guild.id, member.id)
    count = len(rows)
    await interaction.response.send_message(f"{member.mention} warned. Total warns: {count}. Reason: {reason}")
    await safe_dm(member, f"You received a warning in *{interaction.guild.name}*.\nReason: {reason}\nModerator: {interaction.user}\nTotal warns: {count}")
    await post_modlog(interaction.guild, f"{interaction.user} warned {member} — {reason} (Total warns: {count})")
    if count >= 3:
        try:
            until = datetime.utcnow() + timedelta(hours=1)
            await member.edit(timeout=until)
            await interaction.followup.send(f"{member.mention} timed out for 1 hour (3 warnings).")
            await post_modlog(interaction.guild, f"{member} timed out for 1 hour after 3 warnings.")
            await safe_dm(member, f"You have been timed out in *{interaction.guild.name}* for 1 hour after 3 warnings.")
        except Exception:
            logger.exception("Failed to timeout member on 3 warns (slash)")

# Warnings
@tree.command(name="warnings", description="Show a member's warnings")
@app_commands.describe(member="Member to check")
async def warnings_slash(interaction: discord.Interaction, member: discord.Member = None):
    target = member or interaction.user
    if target != interaction.user and not is_moderator(interaction.user):
        await interaction.response.send_message("You don't have permission to view others' warnings.", ephemeral=True)
        return
    rows = get_warns_db(interaction.guild.id, target.id)
    embed = discord.Embed(title=f"Warnings for {target}", description=f"Total: {len(rows)}")
    embed.add_field(name="Recent warns (latest first)", value=format_warns_for_embed(rows), inline=False)
    await interaction.response.send_message(embed=embed)

# Timeout
@tree.command(name="timeout", description="Timeout a member")
@app_commands.describe(member="Member to timeout", minutes="Minutes of timeout")
async def timeout_slash(interaction: discord.Interaction, member: discord.Member, minutes: int = 60):
    if not interaction.user.guild_permissions.moderate_members:
        await interaction.response.send_message("You don't have permission.", ephemeral=True)
        return
    try:
        until = datetime.utcnow() + timedelta(minutes=minutes)
        await member.edit(timeout=until)
        await interaction.response.send_message(f"{member.mention} timed out for {minutes} minutes.")
        await post_modlog(interaction.guild, f"{interaction.user} timed out {member} for {minutes} minutes.")
        await safe_dm(member, f"You were timed out in *{interaction.guild.name}* for {minutes} minutes.\nModerator: {interaction.user}")
    except Exception as e:
        await interaction.response.send_message(f"Failed to timeout: {e}")

# Remove Timeout
@tree.command(name="remove_timeout", description="Remove timeout from a member")
@app_commands.describe(member="Member to remove timeout")
async def remove_timeout_slash(interaction: discord.Interaction, member: discord.Member):
    if not interaction.user.guild_permissions.moderate_members:
        await interaction.response.send_message("You don't have permission.", ephemeral=True)
        return
    try:
        await member.edit(timeout=None)
        await interaction.response.send_message(f"Timeout removed for {member.mention}.")
        await post_modlog(interaction.guild, f"{interaction.user} removed timeout for {member}.")
        await safe_dm(member, f"Your timeout has been removed in *{interaction.guild.name}* by {interaction.user}.")
    except Exception as e:
        await interaction.response.send_message(f"Failed to remove timeout: {e}")

# ---------- ERROR HANDLING ----------
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

# ---------- BOT RUN ----------
if __name__ == "__main__":
    keep_alive()  # start web server for Render
    bot.run(TOKEN)