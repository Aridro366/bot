import discord
from discord.ext import commands
import logging
from dotenv import load_dotenv
import os

load_dotenv()
token = os.getenv('DISCORD_TOKEN')
print("Token loaded:", token)  # For debugging

handler = logging.FileHandler(filename='discord.log', encoding='utf-8', mode='w')
intents = discord.Intents.default()
intents.message_content = True
intents.members = True

bot = commands.Bot(command_prefix='!', intents=intents)

@bot.event
async def on_ready():
    print(f"We are ready to go in, {bot.user.name}")

@bot.event
async def on_member_join(member):
    await member.send(
        f"Welcome to Royal Empire @{member.name}.. "
        f"Need help? write 'help' in https://discord.com/channels/1396670355422056609/1396801885322739743 "
    )

bad_words = [
    "bullshit", "fuck", "fucking", "fucked","bitch", "bitches",
    "ass", "asshole", "crap", "dick", "dicks", "piss", "pissed",
    "cock", "cocksucker", "cum", "naked", "nude", "slut", "whore", "fag",
    "faggot", "retard", "moron", "bastard",
    "twat", "prick", "bloody", "bugger", "bollocks", "arse", "shithead",
    "motherfucker", "son of a bitch", "jerk", "suck", "sucks", "sucker",
    "sexy", "porn", "sex", "semen", "orgy", "rape", "hooker", "prostitute",
    "anal", "beastiality", "incest", "masturbate", "penis", "vagina", "tit",
    "tits", "boobs", "clit", "pussy", "cumshot", "hardcore",
    "xxx", "fuckface", "shitfuck", "assface", "shitbag", "cunt", "slutty",
    "whorehouse", "cockhead", "nigger", "chink", "spic", "kike", "beaner",
    "redneck", "hillbilly", "terrorist", "bomb", "kill", "murder", "weapon",
    "gun", "knife", "hate", "racist", "extremist", "pedophile", "child abuse",
    "scam", "phishing", "clickbait", "malware", "virus", "spyware", "hack",
    "darkweb", "botnet", "free money", "win cash", "get rich", "visit this site",
    "bit.ly", "tinyurl", "goo.gl", "http", "www", "xxxvideos", "escort", "camgirl", "onlyfans"
]

@bot.event
async def on_message(message):
    if message.author == bot.user:
        return

    msg_content = message.content.lower()
    for word in bad_words:
        if word in msg_content:
            await message.delete()
            await message.channel.send(
                f"{message.author.mention} - Please avoid using inappropriate words!"
            )
            return  # ✅ stop after first match

    await bot.process_commands(message)

# ✅ Make help a proper command
@bot.command(name="help")
async def help_command(ctx):
    await ctx.send(
        f"Hello {ctx.author.mention}! Welcome to the server \n"
        f"You can take roles from https://discord.com/channels/1396670355422056609/1396726703564525688 \n"
        f"And ping Staff in https://discord.com/channels/1396670355422056609/1396801885322739743 for further assistance"
    )

from datetime import timedelta

# Kick command
@bot.command()
@commands.has_permissions(kick_members=True)
async def kick(ctx, member: discord.Member, *, reason="No reason provided"):
    await member.kick(reason=reason)
    await ctx.send(f"👢 {member.mention} has been kicked. Reason: {reason}")

# Ban command
@bot.command()
@commands.has_permissions(ban_members=True)
async def ban(ctx, member: discord.Member, *, reason="No reason provided"):
    await member.ban(reason=reason)
    await ctx.send(f"🔨 {member.mention} has been banned. Reason: {reason}")

# Unban command
@bot.command()
@commands.has_permissions(ban_members=True)
async def unban(ctx, *, username: str):
    banned_users = await ctx.guild.bans()
    for ban_entry in banned_users:
        user = ban_entry.user
        if (str(user) == username):
            await ctx.guild.unban(user)
            await ctx.send(f"✅ Unbanned {user.name}")
            return
    await ctx.send("❌ User not found in ban list.")

# Timeout (mute) command
@bot.command()
@commands.has_permissions(moderate_members=True)
async def timeout(ctx, member: discord.Member, minutes: int, *, reason="No reason provided"):
    duration = timedelta(minutes=minutes)
    await member.timeout(duration, reason=reason)
    await ctx.send(f"⏳ {member.mention} has been timed out for {minutes} minutes. Reason: {reason}")

# Untimeout command
@bot.command()
@commands.has_permissions(moderate_members=True)
async def untimeout(ctx, member: discord.Member):
    await member.timeout(None)
    await ctx.send(f"✅ {member.mention} has been removed from timeout.")

# Warn system
warnings = {}

@bot.command()
@commands.has_permissions(manage_messages=True)
async def warn(ctx, member: discord.Member, *, reason="No reason provided"):
    user_id = str(member.id)
    if user_id not in warnings:
        warnings[user_id] = []
    warnings[user_id].append(reason)

    await ctx.send(f"⚠️ {member.mention} has been warned. Reason: {reason} (Total warnings: {len(warnings[user_id])})")

    if len(warnings[user_id]) >= 3:
        await member.timeout(timedelta(minutes=10), reason="3 warnings")
        await ctx.send(f"⏳ {member.mention} has been auto-timed out for 10 minutes (3 warnings).")

# Lockdown (Admins only)
@bot.command()
@commands.has_permissions(administrator=True)  # only admins
async def lockdown(ctx):
    for channel in ctx.guild.text_channels:
        await channel.set_permissions(ctx.guild.default_role, send_messages=False)
    await ctx.send("🔒 **Server is now in lockdown mode!** Only admins can lift it.")

# Unlock
@bot.command()
@commands.has_permissions(administrator=True)  # only admins
async def unlock(ctx):
    for channel in ctx.guild.text_channels:
        await channel.set_permissions(ctx.guild.default_role, send_messages=True)
    await ctx.send("🔓 **Server lockdown lifted!** Everyone can chat again.")


bot.run(token, log_handler=handler, log_level=logging.DEBUG)