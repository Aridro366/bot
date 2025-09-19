# main.py (Part 1/2) - fixed
import os
import re
import logging
import sqlite3
from datetime import datetime, timedelta
from threading import Thread

from dotenv import load_dotenv
import discord
from discord.ext import commands
from flask import Flask

# ---------------- Load ENV ----------------
load_dotenv()
TOKEN = os.getenv("DISCORD_TOKEN")
PREFIX = os.getenv("COMMAND_PREFIX", "?")
DB_FILE = os.getenv("SQLITE_FILE", "bot_data.db")

# ---------------- Logging ----------------
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("mod-bot")

# ---------------- DB Init ----------------
def init_db():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    # Warns
    c.execute("""CREATE TABLE IF NOT EXISTS warns (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        guild_id INTEGER,
        user_id INTEGER,
        moderator_id INTEGER,
        reason TEXT,
        timestamp TEXT
    )""")
    # Filter words
    c.execute("""CREATE TABLE IF NOT EXISTS filter_words (
        guild_id INTEGER,
        word TEXT
    )""")
    # Config (welcome channel, rules, roles, intro, modlog)
    c.execute("""CREATE TABLE IF NOT EXISTS guild_config (
        guild_id INTEGER PRIMARY KEY,
        welcome_channel INTEGER,
        rules_channel INTEGER,
        roles_channel INTEGER,
        intro_channel INTEGER,
        modlog_channel INTEGER
    )""")
    conn.commit()
    conn.close()
init_db()

# ---------------- Discord Setup ----------------
intents = discord.Intents.default()
intents.message_content = True
intents.members = True
intents.guilds = True
bot = commands.Bot(command_prefix=PREFIX, intents=intents, help_command=None)

# ---------------- Keep Alive ----------------
app = Flask("keepalive")
@app.route("/")
def home():
    return "Bot is alive!"

def run_web():
    port = int(os.getenv("PORT", 8080))
    app.run(host="0.0.0.0", port=port)

def start_keep_alive():
    t = Thread(target=run_web, daemon=True)
    t.start()

# wrapper used by Part 2
def keep_alive():
    start_keep_alive()

# ---------------- DB Helpers ----------------
def add_warn(guild_id, user_id, mod_id, reason):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("INSERT INTO warns (guild_id,user_id,moderator_id,reason,timestamp) VALUES(?,?,?,?,?)",
              (guild_id, user_id, mod_id, reason, datetime.utcnow().isoformat()))
    conn.commit(); conn.close()

def get_warns(guild_id, user_id):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("SELECT * FROM warns WHERE guild_id=? AND user_id=?", (guild_id, user_id))
    rows = c.fetchall(); conn.close(); return rows

def add_filter_word(guild_id, word):
    conn = sqlite3.connect(DB_FILE); c = conn.cursor()
    c.execute("INSERT INTO filter_words (guild_id,word) VALUES(?,?)", (guild_id, word.lower()))
    conn.commit(); conn.close()

def remove_filter_word(guild_id, word):
    conn = sqlite3.connect(DB_FILE); c = conn.cursor()
    c.execute("DELETE FROM filter_words WHERE guild_id=? AND word=?", (guild_id, word.lower()))
    conn.commit(); conn.close()

def get_filter_words(guild_id):
    conn = sqlite3.connect(DB_FILE); c = conn.cursor()
    c.execute("SELECT word FROM filter_words WHERE guild_id=?", (guild_id,))
    rows = [r[0] for r in c.fetchall()]; conn.close(); return rows

def set_config(guild_id, **kwargs):
    conn = sqlite3.connect(DB_FILE); c = conn.cursor()
    # ensure row exists
    c.execute("INSERT OR IGNORE INTO guild_config(guild_id,welcome_channel,rules_channel,roles_channel,intro_channel,modlog_channel) VALUES(?,?,?,?,?,?)",
              (guild_id,0,0,0,0,0))
    for key,val in kwargs.items():
        if key in ("welcome_channel","rules_channel","roles_channel","intro_channel","modlog_channel"):
            c.execute(f"UPDATE guild_config SET {key}=? WHERE guild_id=?", (int(val),guild_id))
    conn.commit(); conn.close()

def get_config(guild_id):
    conn = sqlite3.connect(DB_FILE); c = conn.cursor()
    c.execute("SELECT guild_id,welcome_channel,rules_channel,roles_channel,intro_channel,modlog_channel FROM guild_config WHERE guild_id=?", (guild_id,))
    row = c.fetchone(); conn.close()
    if not row: return None
    keys = ["guild_id","welcome_channel","rules_channel","roles_channel","intro_channel","modlog_channel"]
    return dict(zip(keys,row))

# ---------------- Permissions ----------------
def is_mod(member):
    return member.guild_permissions.manage_messages or member.guild_permissions.administrator

# ---------- Utilities ----------
async def safe_dm(user: discord.User, content: str):
    try:
        await user.send(content)
        return True
    except Exception:
        return False

async def post_modlog(guild: discord.Guild, content: str, embed: discord.Embed = None):
    cfg = get_config(guild.id)
    if not cfg: return
    modlog_id = cfg.get("modlog_channel") or 0
    if not modlog_id: return
    ch = guild.get_channel(modlog_id)
    if not ch: return
    try:
        if embed:
            await ch.send(content=content, embed=embed)
        else:
            await ch.send(content)
    except Exception:
        logger.exception("Failed to post modlog")

# ---------------- Events ----------------
@bot.event
async def on_ready():
    logger.info(f"Bot online as {bot.user}")
    try:
        await bot.change_presence(activity=discord.Game(name=f"{PREFIX}help"))
    except Exception:
        pass

# Welcome & filters & auto-warn
@bot.event
async def on_member_join(member):
    cfg = get_config(member.guild.id)
    if not cfg or not cfg.get("welcome_channel"):
        return
    ch = member.guild.get_channel(cfg["welcome_channel"])
    if not ch:
        return
    embed = discord.Embed(title="🎉 Welcome to Royals Empire 🍻",
                          description=f"Hey {member.mention} 👑\nYou’ve just stepped into the kingdom of vibes, loyalty, and legends.\nWe're hyped to have you with us!",
                          color=discord.Color.gold())
    fields = []
    if cfg.get("rules_channel"):
        fields.append(f"🔹 Read the rules in <#{cfg['rules_channel']}>")
    if cfg.get("roles_channel"):
        fields.append(f"🔹 Get your roles from <#{cfg['roles_channel']}>")
    if cfg.get("intro_channel"):
        fields.append(f"🔹 Say hi in <#{cfg['intro_channel']}>")
    if fields:
        embed.add_field(name="Make sure to:", value="\n".join(fields), inline=False)
    embed.set_footer(text=f"Member ID: {member.id}")
    try:
        await ch.send(content=f"Welcome {member.mention}!", embed=embed)
    except Exception:
        logger.exception("Failed to send welcome embed")

@bot.event
async def on_message(msg):
    if msg.author.bot or not msg.guild:
        return
    if is_mod(msg.author):
        await bot.process_commands(msg); return

    # Link filter
    if re.search(r"(https?://\S+|www\.\S+)", msg.content, re.IGNORECASE):
        try:
            await msg.delete()
        except Exception:
            pass
        reason = "Posted a link"
        add_warn(msg.guild.id, msg.author.id, 0, reason)  # moderator id 0 = autobot
        warns = get_warns(msg.guild.id, msg.author.id)
        await safe_dm(msg.author, f"You were warned in *{msg.guild.name}*.\nReason: {reason}\nModerator: AutoFilter\nTotal warns: {len(warns)}")
        await post_modlog(msg.guild, f"Auto-warn: {msg.author} — {reason}")
        if len(warns) >= 3:
            try:
                until = datetime.utcnow() + timedelta(hours=1)
                await msg.author.edit(timeout=until)
                await post_modlog(msg.guild, f"{msg.author} timed out for 1 hour (3 warns)")
                await safe_dm(msg.author, f"You have been timed out in *{msg.guild.name}* for 1 hour after 3 warnings.")
            except Exception:
                logger.exception("Failed to timeout on 3 warns")
        return

    # Word filter
    bad_words = get_filter_words(msg.guild.id)
    msg_lower = msg.content.lower()
    for word in bad_words:
        if re.search(rf"\b{re.escape(word)}\b", msg_lower):
            try:
                await msg.delete()
            except Exception:
                pass
            reason = f"Used banned word: {word}"
            add_warn(msg.guild.id, msg.author.id, 0, reason)
            warns = get_warns(msg.guild.id, msg.author.id)
            await safe_dm(msg.author, f"You were warned in *{msg.guild.name}*.\nReason: {reason}\nModerator: AutoFilter\nTotal warns: {len(warns)}")
            await post_modlog(msg.guild, f"Auto-warn: {msg.author} — {reason}")
            if len(warns) >= 3:
                try:
                    until = datetime.utcnow() + timedelta(hours=1)
                    await msg.author.edit(timeout=until)
                    await post_modlog(msg.guild, f"{msg.author} timed out for 1 hour (3 warns)")
                    await safe_dm(msg.author, f"You have been timed out in *{msg.guild.name}* for 1 hour after 3 warnings.")
                except Exception:
                    logger.exception("Failed to timeout on 3 warns (word filter)")
            return
    await bot.process_commands(msg)

# main.py (Part 2/2) - fixed (commands + run)
# ----------------- Commands: help + moderation -----------------
class HelpView(discord.ui.View):
    def _init_(self):
        super()._init_(timeout=None)
    @discord.ui.button(label="Moderation", style=discord.ButtonStyle.primary, custom_id="help:moderation")
    async def mod_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        embed = discord.Embed(title="Moderation Commands", description=(
            f"{PREFIX}kick <member> [reason]\n"
            f"{PREFIX}ban <member> [reason]\n"
            f"{PREFIX}unban <user_id>\n"
            f"{PREFIX}warn <member> [reason]\n"
            f"{PREFIX}warnings <member>\n"
            f"{PREFIX}timeout <member> <minutes>\n"
            f"{PREFIX}remove_timeout <member>\n"
        ))
        await interaction.response.edit_message(embed=embed, view=self)
    @discord.ui.button(label="Info", style=discord.ButtonStyle.secondary, custom_id="help:info")
    async def info_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        embed = discord.Embed(title="Info Commands", description=(
            f"{PREFIX}avatar <member>\n"
            f"{PREFIX}serverinfo\n"
            f"{PREFIX}memberinfo <member> (admins only)\n"
            f"{PREFIX}roleinfo <role> (admins only)\n"
        ))
        await interaction.response.edit_message(embed=embed, view=self)

@bot.command(name="help")
async def help_cmd(ctx: commands.Context):
    embed = discord.Embed(title="Bot Help", description="Click the buttons below to view different command categories.")
    view = HelpView()
    await ctx.send(embed=embed, view=view)

# Kick
@bot.command(name="kick")
@commands.has_permissions(kick_members=True)
async def kick_cmd(ctx: commands.Context, member: discord.Member, *, reason: str = "No reason provided"):
    try:
        await safe_dm(member, f"You were kicked from *{ctx.guild.name}*.\nReason: {reason}\nModerator: {ctx.author}")
    except: pass
    try:
        await member.kick(reason=reason)
        await ctx.send(f"{member} was kicked. Reason: {reason}")
        await post_modlog(ctx.guild, f"{ctx.author} kicked {member} — {reason}")
    except Exception as e:
        await ctx.send(f"Failed to kick: {e}")

# Ban
@bot.command(name="ban")
@commands.has_permissions(ban_members=True)
async def ban_cmd(ctx: commands.Context, member: discord.Member, *, reason: str = "No reason provided"):
    try:
        await safe_dm(member, f"You have been banned from *{ctx.guild.name}*.\nReason: {reason}\nModerator: {ctx.author}")
    except: pass
    try:
        await member.ban(reason=reason)
        await ctx.send(f"{member} was banned. Reason: {reason}")
        await post_modlog(ctx.guild, f"{ctx.author} banned {member} — {reason}")
    except Exception as e:
        await ctx.send(f"Failed to ban: {e}")

# Unban
@bot.command(name="unban")
@commands.has_permissions(ban_members=True)
async def unban_cmd(ctx: commands.Context, user_id: int):
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
async def warn_cmd(ctx: commands.Context, member: discord.Member, *, reason: str = "Rule break"):
    add_warn(ctx.guild.id, member.id, ctx.author.id, reason)
    warns = get_warns(ctx.guild.id, member.id)
    count = len(warns)
    await ctx.send(f"{member.mention} has been warned. Total warns: {count}. Reason: {reason}")
    await safe_dm(member, f"You have received a warning in *{ctx.guild.name}*.\nReason: {reason}\nModerator: {ctx.author}\nTotal warns: {count}")
    await post_modlog(ctx.guild, f"{ctx.author} warned {member} — {reason} (Total warns: {count})")
    if count >= 3:
        try:
            until = datetime.utcnow() + timedelta(hours=1)
            await member.edit(timeout=until)
            await ctx.send(f"{member.mention} has been timed out for 1 hour (3 warnings).")
            await post_modlog(ctx.guild, f"{member} was timed out for 1 hour (3 warns).")
            await safe_dm(member, f"You have been timed out in *{ctx.guild.name}* for 1 hour after reaching 3 warnings.")
        except Exception:
            logger.exception("Failed to timeout member on 3 warns (manual).")

# Warnings
@bot.command(name="warnings")
async def warnings_cmd(ctx: commands.Context, member: discord.Member = None):
    target = member or ctx.author
    if target != ctx.author and not is_mod(ctx.author):
        await ctx.send("You don't have permission to view other members' warnings.")
        return
    rows = get_warns(ctx.guild.id, target.id)
    count = len(rows)
    embed = discord.Embed(title=f"Warnings for {target}", description=f"Total: {count}")
    if rows:
        text = ""
        for r in rows[:10]:
            wid, g, mod_id, reason, ts = r
            mod_display = "AutoFilter" if mod_id == 0 else f"<@{mod_id}>"
            text += f"ID {wid} • By {mod_display} • {reason} • {ts}\n"
        embed.add_field(name="Recent warns (latest first)", value=text, inline=False)
    await ctx.send(embed=embed)

# Timeout
@bot.command(name="timeout")
@commands.has_permissions(moderate_members=True)
async def timeout_cmd(ctx: commands.Context, member: discord.Member, minutes: int = 60):
    try:
        until = datetime.utcnow() + timedelta(minutes=minutes)
        await member.edit(timeout=until)
        await ctx.send(f"{member.mention} has been timed out for {minutes} minutes.")
        await post_modlog(ctx.guild, f"{ctx.author} timed out {member} for {minutes} minutes.")
        await safe_dm(member, f"You were timed out in *{ctx.guild.name}* for {minutes} minutes.\nModerator: {ctx.author}")
    except Exception as e:
        await ctx.send(f"Failed to timeout: {e}")

# Remove timeout
@bot.command(name="remove_timeout")
@commands.has_permissions(moderate_members=True)
async def remove_timeout_cmd(ctx: commands.Context, member: discord.Member):
    try:
        await member.edit(timeout=None)
        await ctx.send(f"Timeout removed for {member.mention}.")
        await post_modlog(ctx.guild, f"{ctx.author} removed timeout for {member}.")
        await safe_dm(member, f"Your timeout has been removed in *{ctx.guild.name}*.\nModerator: {ctx.author}")
    except Exception as e:
        await ctx.send(f"Failed to remove timeout: {e}")

# Avatar, serverinfo, memberinfo, roleinfo (prefix commands)
@bot.command(name="avatar")
async def avatar_cmd(ctx: commands.Context, member: discord.Member = None):
    m = member or ctx.author
    await ctx.send(f"{m.display_name}'s avatar: {m.display_avatar.url}")

@bot.command(name="serverinfo")
async def serverinfo_cmd(ctx: commands.Context):
    g = ctx.guild
    embed = discord.Embed(title=g.name, description=g.description or "No description", timestamp=g.created_at)
    embed.add_field(name="Members", value=str(g.member_count))
    embed.add_field(name="Owner", value=str(g.owner))
    if g.icon:
        embed.set_thumbnail(url=g.icon.url)
    await ctx.send(embed=embed)

@bot.command(name="memberinfo")
@commands.has_permissions(administrator=True)
async def memberinfo_cmd(ctx: commands.Context, member: discord.Member):
    embed = discord.Embed(title=f"{member}", description=f"ID: {member.id}")
    embed.add_field(name="Joined", value=str(member.joined_at))
    embed.add_field(name="Created", value=str(member.created_at))
    embed.add_field(name="Roles", value=" ".join([r.mention for r in member.roles[1:]]) or "None")
    if member.avatar:
        embed.set_thumbnail(url=member.avatar.url)
    await ctx.send(embed=embed)

@bot.command(name="roleinfo")
@commands.has_permissions(administrator=True)
async def roleinfo_cmd(ctx: commands.Context, role: discord.Role):
    embed = discord.Embed(title=f"{role.name}", description=f"ID: {role.id}")
    embed.add_field(name="Members with role", value=str(len(role.members)))
    embed.add_field(name="Position", value=str(role.position))
    await ctx.send(embed=embed)

# Filter management and config commands
@bot.command(name="add_filter")
@commands.has_permissions(manage_guild=True)
async def add_filter_cmd(ctx: commands.Context, word: str):
    add_filter_word(ctx.guild.id, word)
    await ctx.send(f"Added filter word: {word}")
    await post_modlog(ctx.guild, f"{ctx.author} added filter word {word}.")

@bot.command(name="remove_filter")
@commands.has_permissions(manage_guild=True)
async def remove_filter_cmd(ctx: commands.Context, word: str):
    remove_filter_word(ctx.guild.id, word)
    await ctx.send(f"Removed filter word: {word}")
    await post_modlog(ctx.guild, f"{ctx.author} removed filter word {word}.")

@bot.command(name="list_filters")
@commands.has_permissions(manage_guild=True)
async def list_filters_cmd(ctx: commands.Context):
    words = get_filter_words(ctx.guild.id)
    if not words:
        await ctx.send("No filter words set for this server.")
        return
    text = ", ".join(words)
    if len(text) > 1900:
        with open("filters.txt", "w", encoding="utf8") as f:
            f.write(text)
        await ctx.send(file=discord.File("filters.txt"))
        os.remove("filters.txt")
    else:
        await ctx.send(f"Filter words ({len(words)}): {text}")

@bot.command(name="setwelcome")
@commands.has_permissions(manage_guild=True)
async def setwelcome_cmd(ctx: commands.Context, welcome_channel: discord.TextChannel = None,
                                        rules_channel: discord.TextChannel = None,
                                        roles_channel: discord.TextChannel = None,
                                        intro_channel: discord.TextChannel = None):
    kwargs = {}
    if welcome_channel:
        kwargs["welcome_channel"] = welcome_channel.id
    if rules_channel:
        kwargs["rules_channel"] = rules_channel.id
    if roles_channel:
        kwargs["roles_channel"] = roles_channel.id
    if intro_channel:
        kwargs["intro_channel"] = intro_channel.id
    if kwargs:
        set_config(ctx.guild.id, **kwargs)
        await ctx.send("Updated welcome/rules/roles/intro channel settings for this server.")
        await post_modlog(ctx.guild, f"{ctx.author} updated welcome/rules/roles/intro channels.")
    else:
        await ctx.send("Provide at least one channel to set (welcome/rules/roles/intro).")

@bot.command(name="setmodlog")
@commands.has_permissions(manage_guild=True)
async def setmodlog_cmd(ctx: commands.Context, channel: discord.TextChannel = None):
    if channel:
        set_config(ctx.guild.id, modlog_channel=channel.id)
        await ctx.send(f"Mod-log channel set to {channel.mention}")
        await post_modlog(ctx.guild, f"{ctx.author} set mod-log channel to {channel.mention}")
    else:
        set_config(ctx.guild.id, modlog_channel=0)
        await ctx.send("Mod-log channel cleared.")
        await post_modlog(ctx.guild, f"{ctx.author} cleared mod-log channel.")

# Error handler
@bot.event
async def on_command_error(ctx, error):
    if isinstance(error, commands.MissingPermissions):
        await ctx.send("You don't have permission to run that command.")
    elif isinstance(error, commands.MissingRequiredArgument):
        await ctx.send("Missing argument. Check usage.")
    elif isinstance(error, commands.BadArgument):
        await ctx.send("Bad argument. Check the command and try again.")
    else:
        logger.exception("Command error: %s", error)

# ----------------- Run Bot -----------------
if __name__ == "__main__":
    if not TOKEN:
        logger.error("DISCORD_TOKEN not set in environment.")
        raise SystemExit("DISCORD_TOKEN not set.")
    keep_alive()
    bot.run(TOKEN)