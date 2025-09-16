import discord
from discord.ext import commands
import logging
from dotenv import load_dotenv
import os

# ================== Setup ==================
load_dotenv()
token = os.getenv("DISCORD_TOKEN")
print("Token loaded:", token)  # Debugging

handler = logging.FileHandler(filename="discord.log", encoding="utf-8", mode="w")
intents = discord.Intents.default()
intents.message_content = True
intents.members = True

bot = commands.Bot(command_prefix="!", intents=intents, help_command=None)  # disable default help


# ================== Events ==================
@bot.event
async def on_ready():
    print(f"✅ We are ready to go in as {bot.user.name}")


@bot.event
async def on_member_join(member):
    try:
        await member.send(
            f"👋 Welcome to **Royal Empire** @{member.name}! \n"
            f"Need help? Type `!help` in the support channel."
        )
    except discord.Forbidden:
        print(f"⚠️ Couldn't DM {member.name}")


# ================== Bad Word Filter ==================
bad_words = [
    "bullshit", "fuck", "fucking", "fucked", "bitch", "bitches",
    "ass", "asshole", "crap", "dick", "dicks", "piss", "pissed",
    "cock", "cocksucker", "cum", "naked", "nude", "slut", "whore",
    "fag", "faggot", "retard", "moron", "bastard", "twat", "prick",
    "bloody", "bugger", "bollocks", "arse", "shithead", "motherfucker",
    "son of a bitch", "jerk", "suck", "sucks", "sucker", "sexy", "porn",
    "sex", "semen", "orgy", "rape", "hooker", "prostitute", "anal",
    "beastiality", "incest", "masturbate", "penis", "vagina", "tit",
    "tits", "boobs", "clit", "pussy", "cumshot", "hardcore", "xxx",
    "fuckface", "shitfuck", "assface", "shitbag", "cunt", "slutty",
    "whorehouse", "cockhead", "nigger", "chink", "spic", "kike",
    "beaner", "redneck", "hillbilly", "terrorist", "bomb", "kill",
    "murder", "weapon", "gun", "knife", "hate", "racist", "extremist",
    "pedophile", "child abuse", "scam", "phishing", "clickbait",
    "malware", "virus", "spyware", "hack", "darkweb", "botnet",
    "free money", "win cash", "get rich", "visit this site",
    "bit.ly", "tinyurl", "goo.gl", "http", "www", "xxxvideos",
    "escort", "camgirl", "onlyfans"
]

@bot.event
async def on_message(message):
    if message.author == bot.user:
        return

    msg_content = message.content.lower()

    for word in bad_words:
        if word in msg_content:
            try:
                await message.delete()
                await message.channel.send(
                    f"{message.author.mention} 🚫 Please avoid using inappropriate words!"
                )
            except discord.Forbidden:
                print("⚠️ Missing permission to delete messages")
            return  # stop after first bad word

    await bot.process_commands(message)


# ================== Commands ==================
@bot.command(name="help")
async def custom_help(ctx):
    await ctx.send(
        f"📌 **Help Menu**\n"
        f"Hello {ctx.author.mention}, here’s what I can do:\n\n"
        f"🔹 `!kick @user [reason]` → Kick a member\n"
        f"🔹 `!ban @user [reason]` → Ban a member\n"
        f"🔹 `!timeout @user <seconds>` → Timeout a member\n"
        f"🔹 `!clear <number>` → Clear messages\n"
        f"🔹 `!lock` → (Admin only) Lock a channel\n\n"
        f"You can also take roles here: <#1396726703564525688>\n"
        f"Need help? Ping staff in <#1396801885322739743>"
    )


@bot.command()
@commands.has_permissions(kick_members=True)
async def kick(ctx, member: discord.Member, *, reason="No reason provided"):
    await member.kick(reason=reason)
    await ctx.send(f"👢 {member.mention} has been kicked. Reason: {reason}")


@bot.command()
@commands.has_permissions(ban_members=True)
async def ban(ctx, member: discord.Member, *, reason="No reason provided"):
    await member.ban(reason=reason)
    await ctx.send(f"⛔ {member.mention} has been banned. Reason: {reason}")


@bot.command()
@commands.has_permissions(moderate_members=True)
async def timeout(ctx, member: discord.Member, seconds: int):
    duration = discord.utils.utcnow() + discord.timedelta(seconds=seconds)
    await member.timeout(duration)
    await ctx.send(f"⏳ {member.mention} has been timed out for {seconds} seconds.")


@bot.command()
@commands.has_permissions(manage_messages=True)
async def clear(ctx, amount: int):
    await ctx.channel.purge(limit=amount + 1)
    await ctx.send(f"🧹 Cleared {amount} messages!", delete_after=5)


@bot.command()
@commands.has_permissions(administrator=True)
async def lock(ctx):
    overwrite = ctx.channel.overwrites_for(ctx.guild.default_role)
    overwrite.send_messages = False
    await ctx.channel.set_permissions(ctx.guild.default_role, overwrite=overwrite)
    await ctx.send("🔒 Channel has been locked (Admin only).")


# ================== Run Bot ==================
bot.run(token, log_handler=handler, log_level=logging.DEBUG)
