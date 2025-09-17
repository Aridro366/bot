import os
import re
import logging
from datetime import timedelta
from threading import Thread
from flask import Flask
from dotenv import load_dotenv
import discord
from discord.ext import commands
import yt_dlp

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

# basic logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("bot")
file_handler = logging.FileHandler("bot.log", encoding="utf-8")
logger.addHandler(file_handler)

# ---------------- Intents & Bot ----------------
intents = discord.Intents.default()
intents.members = True
intents.message_content = True

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
            return False, f"{type(e).__name__}: {e}"
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
            return False, f"{type(e).__name__}: {e}"
    return False, f"No compatible un-timeout method found. Last error: {last_exc}"

# ---------------- Events ----------------
@bot.event
async def on_ready():
    print(f"Bot online: {bot.user} (ID: {bot.user.id})")
    logger.info(f"Bot ready: {bot.user} (ID: {bot.user.id})")

@bot.event
async def on_member_join(member):
    try:
        await member.send("Welcome! Type `!help` in the server for commands.")
    except Exception:
        logger.info(f"Could not DM new member: {member}")

@bot.event
async def on_message(message):
    if message.author.bot:
        return

    content = message.content

    for pat in bad_patterns:
        if pat.search(content):
            try:
                await message.delete()
                await message.channel.send(f"{message.author.mention} ⚠️ Please avoid offensive language.", delete_after=6)
            except discord.Forbidden:
                logger.warning("Missing permission.")
            except Exception as e:
                logger.exception("Error filtering bad word")
            return

    await bot.process_commands(message)

@bot.event
async def on_command_error(ctx, error):
    if isinstance(error, commands.MissingPermissions):
        await ctx.send("❌ You don't have permission to use this command.")
    elif isinstance(error, commands.BadArgument):
        await ctx.send("❌ Bad argument. Check your command usage.")
    elif isinstance(error, commands.CommandNotFound):
        return
    else:
        logger.exception("Unhandled error")
        await ctx.send(f"❌ An error occurred: {error}")

# ---------------- Commands ----------------
@bot.command(name="help")
async def custom_help(ctx):
    embed = discord.Embed(title="Help - Moderation Bot", description="Available commands:", color=discord.Color.blurple())
    embed.add_field(name="!kick @user [reason]", value="Kick a member", inline=False)
    embed.add_field(name="!ban @user [reason]", value="Ban a member", inline=False)
    embed.add_field(name="!unban <user_id>", value="Unban by user ID", inline=False)
    embed.add_field(name="!timeout @user <minutes> [reason]", value="Timeout a member", inline=False)
    embed.add_field(name="!remove_timeout @user", value="Remove timeout", inline=False)
    embed.add_field(name="!clear <amount>", value="Clear messages", inline=False)
    embed.add_field(name="!lock", value="Lock the channel", inline=False)
    embed.add_field(name="!unlock", value="Unlock the channel", inline=False)
    await ctx.send(embed=embed)

@bot.command()
@commands.has_permissions(kick_members=True)
async def kick(ctx, member: discord.Member, *, reason="No reason provided"):
    try:
        await member.kick(reason=reason)
        await ctx.send(f"👢 {member.mention} kicked. Reason: {reason}")
    except Exception as e:
        logger.exception("Kick failed")
        await ctx.send(f"❌ Failed to kick: {e}")

@bot.command()
@commands.has_permissions(ban_members=True)
async def ban(ctx, member: discord.Member, *, reason="No reason provided"):
    try:
        await member.ban(reason=reason)
        await ctx.send(f"🔨 {member.mention} banned. Reason: {reason}")
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
        await ctx.send("❗ Minutes must be positive.")
        return
    until = discord.utils.utcnow() + timedelta(minutes=minutes)
    ok, err = await try_apply_timeout(member, until, reason)
    if ok:
        await ctx.send(f"⏳ {member.mention} timed out for {minutes} minute(s). Reason: {reason}")
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
        await ctx.send("❗ Amount must be between 1 and 100.")
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
        logger.exception("Lock failed")
        await ctx.send(f"❌ Failed to lock: {e}")

@bot.command()
@commands.has_permissions(administrator=True)
async def unlock(ctx):
    try:
        overwrite = ctx.channel.overwrites_for(ctx.guild.default_role)
        overwrite.send_messages = True
        await ctx.channel.set_permissions(ctx.guild.default_role, overwrite=overwrite)
        await ctx.send("🔓 Channel unlocked.")
    except Exception as e:
        logger.exception("Unlock failed")
        await ctx.send(f"❌ Failed to unlock: {e}")


# -------- Music Playback --------
@bot.command(name="play")
async def play(ctx, *, search: str):
    if not ctx.author.voice or not ctx.author.voice.channel:
        await ctx.send("🔇 Join a voice channel first!")
        return

    channel = ctx.author.voice.channel
    if ctx.voice_client is None:
        await channel.connect()
    elif ctx.voice_client.channel != channel:
        await ctx.voice_client.move_to(channel)

    ydl_opts = {
        'format': 'bestaudio/best',
        'noplaylist': True,
        'quiet': True,
        'source_address': '0.0.0.0',  # IPv6 issues workaround
    }
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(f"ytsearch:{search}", download=False)
            if not info or 'entries' not in info or len(info['entries']) == 0:
                await ctx.send("⚠️ No results. Try another song.")
                return
            url = info['entries'][0]['url']
            title = info['entries'][0]['title']

        # FFmpeg options for reconnecting streams
        ffmpeg_opts = '-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5'
        source = discord.FFmpegPCMAudio(
            url,
            options=ffmpeg_opts,
            executable="ffmpeg"  # Requires ffmpeg in your PATH
        )

        ctx.voice_client.stop()  # Stop any currently playing audio
        ctx.voice_client.play(source)
        await ctx.send(f"🎶 Now playing: **{title}**")
    except Exception as e:
        await ctx.send(f"❌ Error: {e}")

        @bot.command(name="leave")
        async def leave(ctx):
         if ctx.voice_client:
          await ctx.voice_client.disconnect()
        await ctx.send("👋 Left the voice channel.")
    else:
        await ctx.send("⚠️ Not connected to any voice channel.")

@bot.command(name="stop")
async def stop(ctx):
    if ctx.voice_client:
        ctx.voice_client.stop()
        await ctx.send("⏹️ Playback stopped.")
    else:
        await ctx.send("⚠️ Not connected to any voice channel.")

@bot.command(name="pause")
async def pause(ctx):
    if ctx.voice_client and ctx.voice_client.is_playing():
        ctx.voice_client.pause()
        await ctx.send("⏸️ Paused playback.")
    else:
        await ctx.send("⚠️ Nothing is playing.")

@bot.command(name="resume")
async def resume(ctx):
    if ctx.voice_client and ctx.voice_client.is_paused():
        ctx.voice_client.resume()
        await ctx.send("▶️ Resumed playback.")
    else:
        await ctx.send("⚠️ Playback is not paused.")


# ---------------- Run ----------------
if __name__ == "__main__":
    keep_alive()
    bot.run(TOKEN)