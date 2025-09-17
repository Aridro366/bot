import os
import re
import logging
from datetime import datetime, timedelta
from threading import Thread
from collections import defaultdict, deque
from flask import Flask
from dotenv import load_dotenv
import discord
from discord.ext import commands
import yt_dlp
import asyncio

# ---------------- Keep alive server ----------------
app = Flask('')

@app.route('/')
def home():
    return "Bot is alive!"

def run():
    app.run(host='0.0.0.0', port=8080)

def keep_alive():
    t = Thread(target=run)
    t.start()

# ---------------- Configuration ----------------
load_dotenv()
TOKEN = os.getenv("DISCORD_TOKEN")

if not TOKEN:
    raise SystemExit("ERROR: DISCORD_TOKEN not found in .env")

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("bot")
file_handler = logging.FileHandler("bot.log", encoding="utf-8")
logger.addHandler(file_handler)

# ---------------- Intents & Bot ----------------
intents = discord.Intents.default()
intents.members = True
intents.message_content = True
intents.voice_states = True

bot = commands.Bot(command_prefix="!", intents=intents, help_command=None)

try:
    bot.remove_command("help")
except Exception:
    pass

# ---------------- Bad words list ----------------
bad_words = [
    "shit", "bullshit", "fuck", "fucking", "fucked", "damn", "bitch", "bitches",
    "ass", "asshole", "crap", "dick", "dicks", "piss", "pissed", "hell",
    "cock", "cocksucker", "cum", "naked", "nude", "slut", "whore", "fag",
    "faggot", "retard", "idiot", "stupid", "dumb", "moron", "loser", "bastard",
    "twat", "prick", "bloody", "bugger", "bollocks", "arse", "shithead",
    "motherfucker", "son of a bitch", "jerk", "suck", "sucks", "sucker",
    "sexy", "porn", "sex", "semen", "orgy", "rape", "hooker", "prostitute",
    "anal", "beastiality", "incest", "masturbate", "penis", "vagina", "tit",
    "tits", "boobs", "clit", "pussy", "twat", "cumshot", "hardcore",
    "xxx", "fuckface", "shitfuck", "assface", "shitbag", "cunt", "slutty",
    "whorehouse", "cockhead", "nigger", "chink", "spic", "kike", "beaner",
    "redneck", "hillbilly", "terrorist", "bomb", "kill", "murder", "weapon",
    "gun", "knife", "hate", "racist", "extremist", "pedophile", "child abuse",
    "scam", "phishing", "clickbait", "malware", "virus", "spyware", "hack",
    "darkweb", "botnet", "free money", "win cash", "get rich", "visit this site",
    "bit.ly", "tinyurl", "goo.gl", "http", "www", "click here", "join now",
    "subscribe", "adult", "xxxvideos", "escort", "camgirl", "onlyfans"
]
bad_patterns = [re.compile(re.escape(word), re.IGNORECASE) for word in bad_words]

# ---------------- Anti-Spam Configuration ----------------
SPAM_LIMIT = 5
TIME_FRAME = 10  # seconds
MAX_WARNINGS = 3
TIMEOUT_DURATION = 30 * 60  # 30 minutes

user_messages = defaultdict(lambda: deque(maxlen=SPAM_LIMIT))
user_warnings = defaultdict(int)

# ---------------- Music Queue ----------------
queues = defaultdict(asyncio.Queue)

def get_queue(guild_id):
    return queues[guild_id]

# ---------------- Timeout abstraction ----------------
async def try_apply_timeout(member: discord.Member, until_dt, reason: str):
    attempts = []
    attempts.append(lambda: getattr(member, "timeout")(until_dt))
    attempts.append(lambda: getattr(member, "timeout")(timed_out_until=until_dt, reason=reason))
    attempts.append(lambda: getattr(member, "timeout")(until=until_dt, reason=reason))
    attempts.append(lambda: member.edit(communication_disabled_until=until_dt, reason=reason))

    last_exc = None
    for attempt in attempts:
        try:
            coro = attempt()
            if coro is None:
                continue
            await coro
            return True, None
        except AttributeError as e:
            last_exc = e
            continue
        except TypeError as e:
            last_exc = e
            continue
        except Exception as e:
            logger.exception("Timeout attempt raised exception")
            return False, f"{type(e)._name_}: {e}"
    return False, f"No compatible timeout method found. Last error: {last_exc}"

async def try_remove_timeout(member: discord.Member):
    attempts = []
    attempts.append(lambda: getattr(member, "timeout")(None))
    attempts.append(lambda: member.edit(communication_disabled_until=None, reason="Timeout removed by staff"))

    last_exc = None
    for attempt in attempts:
        try:
            coro = attempt()
            if coro is None:
                continue
            await coro
            return True, None
        except AttributeError as e:
            last_exc = e
            continue
        except TypeError as e:
            last_exc = e
            continue
        except Exception as e:
            logger.exception("Failed to remove timeout")
            return False, f"{type(e)._name_}: {e}"
    return False, f"No compatible un-timeout method found. Last error: {last_exc}"

# ---------------- Events ----------------
@bot.event
async def on_ready():
    print(f"Bot online: {bot.user} (ID: {bot.user.id})")
    logger.info(f"Bot ready: {bot.user} (ID: {bot.user.id})")

@bot.event
async def on_member_join(member):
    try:
        await member.send("Welcome! Type !help in the server for commands.")
    except Exception:
        logger.info(f"Could not DM new member: {member}")

@bot.event
async def on_message(message):
    if message.author.bot:
        return

    # Ignore admins for bad word and spam checks
    if message.author.guild_permissions.administrator:
        await bot.process_commands(message)
        return

    content = message.content

    # Bad word filter
    for pat in bad_patterns:
        if pat.search(content):
            try:
                await message.delete()
                await message.channel.send(f"{message.author.mention} ⚠ Please avoid offensive language.", delete_after=6)
            except discord.Forbidden:
                logger.warning("Missing permission to delete or send message.")
            except Exception as e:
                logger.exception("Error filtering bad word")
            return

    # Anti-spam logic
    now = datetime.now()
    user_id = message.author.id
    timestamps = user_messages[user_id]
    timestamps.append(now)

    if len(timestamps) == SPAM_LIMIT:
        if (now - timestamps[0]).total_seconds() <= TIME_FRAME:
            await handle_spam(message)

    await bot.process_commands(message)

async def handle_spam(message):
    user = message.author

    if user.guild_permissions.administrator:
        return

    user_id = user.id
    user_warnings[user_id] += 1
    warnings = user_warnings[user_id]

    if warnings < MAX_WARNINGS:
        await message.channel.send(f"{user.mention}, you are spamming! Warning {warnings}/{MAX_WARNINGS}. Please slow down.")
    else:
        try:
            await message.channel.send(f"{user.mention}, you have been timed out for 30 minutes due to repeated spamming.")
            until = discord.utils.utcnow() + timedelta(seconds=TIMEOUT_DURATION)
            ok, err = await try_apply_timeout(user, until, "Exceeded spam warnings")
            if ok:
                user_warnings[user_id] = 0
            else:
                await message.channel.send(f"⚠ Timeout failed: {err}")
        except Exception as e:
            logger.exception("Error handling spam timeout")
            await message.channel.send(f"⚠ Failed to timeout {user.mention}: {e}")

@bot.event
async def on_command_error(ctx, error):
    if isinstance(error, commands.MissingPermissions):
        await ctx.send("❌ You don't have permission to use this command.")
    elif isinstance(error, commands.BadArgument):
        await ctx.send("❌ Bad argument. Check your command usage.")
    elif isinstance(error, commands.CommandNotFound):
        return
    else:
        logger.exception("Uncaught exception")
        await ctx.send(f"❌ An error occurred: {error}")

# ---------------- Moderation Commands ----------------
@bot.command(name="help")
async def custom_help(ctx):
    embed = discord.Embed(title="Help - Moderation & Music Bot", description="Available commands:", color=discord.Color.blurple())
    embed.add_field(name="!kick @user [reason]", value="Kick a member", inline=False)
    embed.add_field(name="!ban @user [reason]", value="Ban a member", inline=False)
    embed.add_field(name="!unban <user_id>", value="Unban by user ID", inline=False)
    embed.add_field(name="!timeout @user <minutes> [reason]", value="Timeout a member", inline=False)
    embed.add_field(name="!remove_timeout @user", value="Remove timeout", inline=False)
    embed.add_field(name="!clear <amount>", value="Clear messages", inline=False)
    embed.add_field(name="!lock", value="Lock the channel", inline=False)
    embed.add_field(name="!unlock", value="Unlock the channel", inline=False)
    embed.add_field(name="!join", value="Join voice channel", inline=False)
    embed.add_field(name="!leave", value="Leave voice channel", inline=False)
    embed.add_field(name="!play <url>", value="Play music from YouTube URL", inline=False)
    embed.add_field(name="!pause", value="Pause music", inline=False)
    embed.add_field(name="!resume", value="Resume music", inline=False)
    embed.add_field(name="!stop", value="Stop music", inline=False)
    embed.add_field(name="!queue_list", value="Show queued songs", inline=False)
    await ctx.send(embed=embed)

@bot.command()
@commands.has_permissions(kick_members=True)
async def kick(ctx, member: discord.Member, *, reason="No reason provided"):
    try:
        await member.kick(reason=reason)
        await ctx.send(f"👤 {member.mention} kicked. Reason: {reason}")
    except Exception as e:
        logger.exception("Kick failed")
        await ctx.send(f"❌ Failed to kick: {e}")

@bot.command()
@commands.has_permissions(ban_members=True)
async def ban(ctx, member: discord.Member, *, reason="No reason provided"):
    try:
        await member.ban(reason=reason)
        await ctx.send(f"🛑 {member.mention} banned. Reason: {reason}")
    except Exception as e:
        logger.exception("Ban failed")
        await ctx.send(f"❌ Failed to ban: {e}")

@bot.command()
@commands.has_permissions(ban_members=True)
async def unban(ctx, user_id: int):
    try:
        user = await bot.fetch_user(user_id)
        await ctx.guild.unban(user)
        await ctx.send(f"✅ Unbanned {user} (ID: {user_id})")
    except discord.NotFound:
        await ctx.send("❌ User ID not found.")
    except Exception as e:
        logger.exception("Unban failed")
        await ctx.send(f"❌ Failed to unban: {e}")

@bot.command()
@commands.has_permissions(moderate_members=True)
async def timeout(ctx, member: discord.Member, minutes: int, *, reason="No reason provided"):
    if minutes < 0:
        await ctx.send("❌ Minutes must be positive.")
        return
    until = discord.utils.utcnow() + timedelta(minutes=minutes)
    ok, err = await try_apply_timeout(member, until, reason)
    if ok:
        await ctx.send(f"⏱ {member.mention} timed out for {minutes} minute(s). Reason: {reason}")
    else:
        await ctx.send(f"❌ Failed to timeout {member.mention}. {err}")

@bot.command()
@commands.has_permissions(moderate_members=True)
async def remove_timeout(ctx, member: discord.Member):
    ok, err = await try_remove_timeout(member)
    if ok:
        await ctx.send(f"✅ {member.mention} removed from timeout.")
    else:
        await ctx.send(f"❌ Failed to remove timeout: {err}")

@bot.command()
@commands.has_permissions(manage_messages=True)
async def clear(ctx, amount: int):
    if amount < 1 or amount > 100:
        await ctx.send("❌ Amount must be between 1 and 100.")
        return
    try:
        await ctx.channel.purge(limit=amount+1)
        m = await ctx.send(f"🧹 Cleared {amount} messages.")
        try:
            await m.delete(delay=5)
        except Exception:
            pass
    except Exception as e:
        logger.exception("Clear failed")
        await ctx.send(f"❌ Failed to clear messages: {e}")

@bot.command()
@commands.has_permissions(administrator=True)
async def lock(ctx):
    try:
        overwrite = ctx.channel.overwrites_for(ctx.guild.default_role)
        overwrite.send_messages = False
        await ctx.channel.set_permissions(ctx.guild.default_role, overwrite=overwrite)
        await ctx.send("🔒 Channel locked.")
    except Exception as e:
        logger.exception("Lock command failed")

        await ctx.send(f"Failed to lock channel: {e}")

@bot.command()
async def ping(ctx):
    latency = bot.latency
    latency_ms = round(latency * 1000)
    await ctx.send(f"🏓 Pong! Latency: {latency_ms} ms")
