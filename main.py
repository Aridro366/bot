import discord
from discord.ext import commands
from datetime import timedelta

# ====== BOT SETUP ======
intents = discord.Intents.default()
intents.message_content = True
intents.members = True
bot = commands.Bot(command_prefix="!", intents=intents)


# ====== EVENTS ======
@bot.event
async def on_ready():
    print(f"✅ Logged in as {bot.user}")


# ====== HELP COMMAND ======
@bot.command()
async def help(ctx):
    embed = discord.Embed(title="📌 Help Menu", color=discord.Color.blue())
    embed.add_field(name="🔹 !kick @user [reason]", value="Kick a member", inline=False)
    embed.add_field(name="🔹 !ban @user [reason]", value="Ban a member", inline=False)
    embed.add_field(name="🔹 !unban @user <minutes> [reason]", value="Unban a member", inline=False)
    embed.add_field(name="🔹 !clear <number>", value="Clear messages", inline=False)
    embed.add_field(name="🔹 !lock", value="Lock the channel (Admin only)", inline=False)
    embed.add_field(name="🔹 !unlock", value="Unlock the channel (Admin only)", inline=False)
    embed.add_field(name="🔹 !timeout @user <min>", value="Timeout a member", inline=False)
    await ctx.send(embed=embed)


# ====== KICK ======
@bot.command()
@commands.has_permissions(kick_members=True)
async def kick(ctx, member: discord.Member, *, reason="No reason provided"):
    await member.kick(reason=reason)
    await ctx.send(f"👢 {member.mention} was kicked. Reason: {reason}")


# ====== BAN ======
@bot.command()
@commands.has_permissions(ban_members=True)
async def ban(ctx, member: discord.Member, *, reason="No reason provided"):
    await member.ban(reason=reason)
    await ctx.send(f"🔨 {member.mention} was banned. Reason: {reason}")


# ====== CLEAR ======
@bot.command()
@commands.has_permissions(manage_messages=True)
async def clear(ctx, amount: int):
    await ctx.channel.purge(limit=amount + 1)
    await ctx.send(f"🧹 Cleared {amount} messages", delete_after=5)


# ====== LOCK CHANNEL ======
@bot.command()
@commands.has_permissions(administrator=True)
async def lock(ctx):
    overwrite = ctx.channel.overwrites_for(ctx.guild.default_role)
    overwrite.send_messages = False
    await ctx.channel.set_permissions(ctx.guild.default_role, overwrite=overwrite)
    await ctx.send("🔒 Channel locked (Admin only)")


# ====== UNLOCK CHANNEL ======
@bot.command()
@commands.has_permissions(administrator=True)
async def unlock(ctx):
    overwrite = ctx.channel.overwrites_for(ctx.guild.default_role)
    overwrite.send_messages = True
    await ctx.channel.set_permissions(ctx.guild.default_role, overwrite=overwrite)
    await ctx.send("🔓 Channel unlocked (Admin only)")


# timeout
from datetime import timedelta

@bot.command()
@commands.has_permissions(moderate_members=True)
async def timeout(ctx, member: discord.Member, minutes: int, *, reason="No reason provided"):
    """Timeout a member for given minutes (works on your discord.py version)."""
    try:
        until = discord.utils.utcnow() + timedelta(minutes=minutes)
        await member.edit(communication_disabled_until=until, reason=reason)  # FIXED
        await ctx.send(f"⏳ {member.mention} has been timed out for {minutes} minute(s). Reason: {reason}")
    except Exception as e:
        await ctx.send(f"❌ Failed to timeout {member.mention}. Error: {e}")


# ====== BAD WORD FILTER ======
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
    if message.author.bot:
        return
    for word in bad_words:
        if word in message.content.lower():
            await message.delete()
            await message.channel.send(f"⚠️ {message.author.mention}, watch your language!", delete_after=5)
            return
    await bot.process_commands(message)

# Unban command
@bot.command()
@commands.has_permissions(ban_members=True)
async def unban(ctx, user_id: int):
    """Unban a user using their ID"""
    try:
        user = await bot.fetch_user(user_id)
        await ctx.guild.unban(user)
        await ctx.send(f"✅ Unbanned {user.mention} (ID: {user.id})")
    except Exception as e:
        await ctx.send(f"❌ Failed to unban user with ID {user_id}. Error: {e}")



# ====== RUN BOT ======
bot.run("DISCORD_TOKEN")





