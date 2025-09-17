# aegis_bot.py
import os
import re
import json
import logging
from datetime import timedelta
from dotenv import load_dotenv

import discord
from discord.ext import commands

# ---------------- Setup & logging ----------------
load_dotenv()
TOKEN = os.getenv("DISCORD_TOKEN")
if not TOKEN:
    raise RuntimeError("DISCORD_TOKEN not set in .env")

logging.basicConfig(level=logging.INFO)
handler = logging.FileHandler(filename="discord.log", encoding="utf-8", mode="a")
logger = logging.getLogger("discord_bot")
logger.setLevel(logging.INFO)
logger.addHandler(handler)

intents = discord.Intents.default()
intents.message_content = True
intents.members = True

bot = commands.Bot(command_prefix="!", intents=intents, help_command=None)
# guarantee default help is removed
try:
    bot.remove_command("help")
except Exception:
    pass

# ---------------- Bad-words loader & compiled patterns ----------------
BAD_WORDS_FILE = "bad_words.txt"

def load_bad_words():
    if os.path.isfile(BAD_WORDS_FILE):
        with open(BAD_WORDS_FILE, "r", encoding="utf-8") as fh:
            words = [ln.strip() for ln in fh if ln.strip() and not ln.strip().startswith("#")]
            return words
    # fallback example list (you can replace by creating bad_words.txt)
    return ["fuck", "shit", "bitch", "ass", "spam", "scam", "porn", "nude", "xxx"]

bad_words = load_bad_words()
# compile regex patterns with word boundaries for safer matching (avoids matching "class" -> "ass")
bad_word_patterns = [re.compile(rf"\b{re.escape(w)}\b", re.IGNORECASE) for w in bad_words]

# ---------------- Persistent warnings ----------------
WARN_FILE = "warnings.json"

def load_warnings():
    if os.path.isfile(WARN_FILE):
        with open(WARN_FILE, "r", encoding="utf-8") as fh:
            return json.load(fh)
    return {}  # {user_id_str: [ { "reason": "...", "by": "...", "ts": "..." }, ... ]}

def save_warnings(w):
    with open(WARN_FILE, "w", encoding="utf-8") as fh:
        json.dump(w, fh, indent=2)

warnings_db = load_warnings()

# ---------------- Events ----------------
@bot.event
async def on_ready():
    logger.info(f"Bot ready: {bot.user} (ID: {bot.user.id})")
    print(f"✅ Bot is online as {bot.user} (ID: {bot.user.id})")

@bot.event
async def on_member_join(member):
    try:
        await member.send(f"👋 Welcome to **Royal Empire**, {member.name}! Need help? Type `!help`.")
    except discord.Forbidden:
        logger.info(f"Couldn't DM {member} (DMs closed).")

@bot.event
async def on_message(message):
    # ignore bots (including self)
    if message.author.bot:
        return

    content = message.content

    # check bad words once and act once
    for pat in bad_word_patterns:
        if pat.search(content):
            try:
                await message.delete()
                warn_msg = await message.channel.send(
                    f"{message.author.mention} 🚫 Please avoid using inappropriate language!"
                )
                # auto-delete the warning after a few seconds so channels don't clutter
                try:
                    await warn_msg.delete(delay=7)
                except Exception:
                    pass
            except discord.Forbidden:
                logger.warning("Missing permission to delete messages or send messages in channel.")
            except Exception as exc:
                logger.exception("Error while handling bad word: %s", exc)
            return  # STOP after first match — prevents multiple replies

    # allow commands to run
    await bot.process_commands(message)

# ---------------- Helper: check permissions errors ----------------
@bot.event
async def on_command_error(ctx, error):
    if isinstance(error, commands.MissingPermissions):
        await ctx.send("❌ You don't have permission to use this command.")
    elif isinstance(error, commands.BadArgument):
        await ctx.send("❌ Bad argument. Check command usage.")
    elif isinstance(error, commands.CommandNotFound):
        # ignore unknown commands silently (optional)
        pass
    else:
        logger.exception("Unhandled command error: %s", error)
        await ctx.send(f"❌ An error occurred: {str(error)}")

# ---------------- Commands ----------------
@bot.command(name="help")
async def custom_help(ctx):
    embed = discord.Embed(title="Aegis Help", color=discord.Color.blue())
    embed.description = "Moderation commands for staff"
    embed.add_field(name="!kick @user [reason]", value="Kick a member", inline=False)
    embed.add_field(name="!ban @user [reason]", value="Ban a member", inline=False)
    embed.add_field(name="!unban <user_id>", value="Unban by user ID", inline=False)
    embed.add_field(name="!timeout @user <minutes> [reason]", value="Timeout (mute) a member", inline=False)
    embed.add_field(name="!untimeout @user", value="Remove timeout", inline=False)
    embed.add_field(name="!warn @user [reason]", value="Add a warning (tracks in warnings.json)", inline=False)
    embed.add_field(name="!warnings @user", value="Show warnings for a user", inline=False)
    embed.add_field(name="!clear <amount>", value="Purge messages", inline=False)
    embed.add_field(name="!lock", value="Lock current channel (Admin only)", inline=False)
    embed.add_field(name="!unlock", value="Unlock current channel (Admin only)", inline=False)
    await ctx.send(embed=embed)

# ----- Kick -----
@bot.command()
@commands.has_permissions(kick_members=True)
async def kick(ctx, member: discord.Member, *, reason: str = "No reason provided"):
    try:
        await member.kick(reason=reason)
        await ctx.send(f"👢 {member.mention} was kicked. Reason: {reason}")
    except Exception as e:
        await ctx.send(f"❌ Failed to kick: {e}")

# ----- Ban -----
@bot.command()
@commands.has_permissions(ban_members=True)
async def ban(ctx, member: discord.Member, *, reason: str = "No reason provided"):
    try:
        await member.ban(reason=reason)
        await ctx.send(f"🔨 {member.mention} was banned. Reason: {reason}")
    except Exception as e:
        await ctx.send(f"❌ Failed to ban: {e}")

# ----- Unban by ID -----
@bot.command()
@commands.has_permissions(ban_members=True)
async def unban(ctx, user_id: int):
    try:
        user = await bot.fetch_user(user_id)
        await ctx.guild.unban(user)
        await ctx.send(f"✅ Unbanned {user} (ID: {user_id})")
    except discord.NotFound:
        await ctx.send("❌ That user ID is not banned / not found.")
    except Exception as e:
        await ctx.send(f"❌ Failed to unban: {e}")

# ----- Timeout (works with discord.py versions expecting communication_disabled_until) -----
@bot.command()
@commands.has_permissions(moderate_members=True)
async def timeout(ctx, member: discord.Member, minutes: int, *, reason: str = "No reason provided"):
    try:
        until = discord.utils.utcnow() + timedelta(minutes=minutes)
        # use member.edit to support the discord.py variant where Member.timeout isn't available
        await member.edit(communication_disabled_until=until, reason=reason)
        await ctx.send(f"⏳ {member.mention} timed out for {minutes} minute(s). Reason: {reason}")
    except Exception as e:
        await ctx.send(f"❌ Failed to timeout {member.mention}. Error: {e}")

@bot.command()
@commands.has_permissions(moderate_members=True)
async def untimeout(ctx, member: discord.Member):
    try:
        await member.edit(communication_disabled_until=None, reason="Timeout removed by staff")
        await ctx.send(f"✅ {member.mention} removed from timeout.")
    except Exception as e:
        await ctx.send(f"❌ Failed to remove timeout: {e}")

# ----- Clear (purge) -----
@bot.command()
@commands.has_permissions(manage_messages=True)
async def clear(ctx, amount: int):
    if amount < 1 or amount > 100:
        await ctx.send("❗ Amount must be between 1 and 100.")
        return
    try:
        await ctx.channel.purge(limit=amount + 1)  # +1 to remove command message
        msg = await ctx.send(f"🧹 Cleared {amount} messages.")
        await msg.delete(delay=5)
    except Exception as e:
        await ctx.send(f"❌ Failed to clear messages: {e}")

# ----- Lock / Unlock (Admin only) -----
@bot.command()
@commands.has_permissions(administrator=True)
async def lock(ctx):
    try:
        overwrite = ctx.channel.overwrites_for(ctx.guild.default_role)
        overwrite.send_messages = False
        await ctx.channel.set_permissions(ctx.guild.default_role, overwrite=overwrite)
        await ctx.send("🔒 Channel locked (Admin only).")
    except Exception as e:
        await ctx.send(f"❌ Failed to lock channel: {e}")

@bot.command()
@commands.has_permissions(administrator=True)
async def unlock(ctx):
    try:
        overwrite = ctx.channel.overwrites_for(ctx.guild.default_role)
        overwrite.send_messages = True
        await ctx.channel.set_permissions(ctx.guild.default_role, overwrite=overwrite)
        await ctx.send("🔓 Channel unlocked (Admin only).")
    except Exception as e:
        await ctx.send(f"❌ Failed to unlock channel: {e}")

# ----- Warn system (persistent) -----
@bot.command()
@commands.has_permissions(manage_messages=True)
async def warn(ctx, member: discord.Member, *, reason: str = "No reason provided"):
    uid = str(member.id)
    entry = { "reason": reason, "by": str(ctx.author), "ts": discord.utils.utcnow().isoformat() }
    warnings_db.setdefault(uid, []).append(entry)
    save_warnings(warnings_db)

    total = len(warnings_db[uid])
    await ctx.send(f"⚠️ {member.mention} has been warned. Reason: {reason} (Total warnings: {total})")

    # auto-action: on >=3 warnings, timeout 10 minutes
    if total >= 3:
        try:
            until = discord.utils.utcnow() + timedelta(minutes=10)
            await member.edit(communication_disabled_until=until, reason="Auto-timeout: 3 warnings")
            await ctx.send(f"⏳ {member.mention} has been auto-timed out for 10 minutes (3 warnings).")
            # optional: reset warnings or leave them
            warnings_db[uid] = []  # reset after auto-action
            save_warnings(warnings_db)
        except Exception as e:
            await ctx.send(f"❌ Failed to auto-timeout after warnings: {e}")

@bot.command()
@commands.has_permissions(manage_messages=True)
async def warnings(ctx, member: discord.Member):
    uid = str(member.id)
    user_warns = warnings_db.get(uid, [])
    if not user_warns:
        await ctx.send(f"{member.mention} has no warnings.")
        return
    # send compact list
    out = [f"{i+1}. {w['reason']} — by {w['by']} at {w['ts']}" for i,w in enumerate(user_warns)]
    # if too long, send as a file
    if sum(len(x) for x in out) > 1800:
        with open("warns_temp.txt", "w", encoding="utf-8") as fh:
            fh.write("\n".join(out))
        await ctx.send(file=discord.File("warns_temp.txt"))
        os.remove("warns_temp.txt")
    else:
        await ctx.send("\n".join(out))

# ---------------- Run ----------------
if __name__ == "__main__":
    print("Starting Aegis bot... (make sure only one instance is running)")
    bot.run(TOKEN)