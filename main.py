import discord
from discord.ext import commands, tasks
from discord import app_commands
import asyncio
import os
from dotenv import load_dotenv
import random
from keep_alive import keep_alive

load_dotenv()
TOKEN = os.getenv("DISCORD_TOKEN")
GUILD_ID = int(os.getenv("GUILD_ID"))
WELCOME_CHANNEL_ID = 1396723539167543346
MOD_CHANNEL= 1404801888368594974

intents = discord.Intents.default()
intents.members = True
intents.message_content = True

bot = commands.Bot(command_prefix="?", intents=intents)
guild = discord.Object(id=GUILD_ID)

bot.remove_command("help")

keep_alive()

# ---------- Helper ----------
def mod_embed(title, description, color=discord.Color.red()):
    return discord.Embed(title=title, description=description, color=color)


# ---------------- MODERATION HELPERS ----------------
async def hierarchy_check(actor: discord.Member, target: discord.Member, ctx_or_interaction):
    """Check if actor can act on target based on role hierarchy."""
    if actor.top_role <= target.top_role:
        msg = f"❌ You cannot act on {target.mention}, their role is equal/higher."
        if isinstance(ctx_or_interaction, commands.Context):
            await ctx_or_interaction.send(content=msg)
        else:
            await ctx_or_interaction.response.send_message(content=msg, ephemeral=False)
        return False
    if ctx_or_interaction.guild.me.top_role <= target.top_role:
        msg = f"❌ I cannot act on {target.mention}, their role is higher than mine."
        if isinstance(ctx_or_interaction, commands.Context):
            await ctx_or_interaction.send(content=msg)
        else:
            await ctx_or_interaction.response.send_message(content=msg, ephemeral=False)
        return False
    return True


async def send_response(ctx_or_interaction, content=None, embed=None):
    """Helper to send a message to ctx or interaction."""
    if isinstance(ctx_or_interaction, commands.Context):
        await ctx_or_interaction.send(content=content, embed=embed)
    else:
        # If slash command, check if already responded
        if ctx_or_interaction.response.is_done():
            await ctx_or_interaction.followup.send(content=content, embed=embed)
        else:
            await ctx_or_interaction.response.send_message(content=content, embed=embed)



# ---------- Status Rotation ----------
status_list = [
    {"type": "playing", "text": "Hosting Royal Empire"},
    {"type": "watching", "text": "over the server"},
    {"type": "listening", "text": "your commands"},
    {"type": "competing", "text": "moderation"},
    {"type": "playing", "text": "?help"},
]

@tasks.loop(seconds=30)
async def change_status():
    status = status_list.pop(0)
    if status["type"] == "playing":
        activity = discord.Game(name=status["text"])
    elif status["type"] == "watching":
        activity = discord.Activity(type=discord.ActivityType.watching, name=status["text"])
    elif status["type"] == "listening":
        activity = discord.Activity(type=discord.ActivityType.listening, name=status["text"])
    elif status["type"] == "competing":
        activity = discord.Activity(type=discord.ActivityType.competing, name=status["text"])
    else:
        activity = None
    await bot.change_presence(status=discord.Status.online, activity=activity)
    status_list.append(status)

# ---------- Autorole ----------
autoroles = {}  # guild_id: role_id

# ---------- Events ----------
@bot.event
async def on_ready():
    print(f"[OK] Logged in as {bot.user} (ID: {bot.user.id})")
    change_status.start()
    try:
        synced = await bot.tree.sync(guild=guild)
        print(f"[OK] Synced {len(synced)} slash commands to guild")
    except Exception as e:
        print(f"[ERR] Slash sync failed: {e}")

@bot.event
async def on_member_join(member: discord.Member):
    # Welcome message
    channel = member.guild.get_channel(WELCOME_CHANNEL_ID)
    if channel:
        welcome_message = f"""
🎉 Welcome to Royals Empire 🍻
━━━━━━━━━━━━━━━━━━━
Hey {member.mention} 👑
You’ve just stepped into the kingdom of vibes, loyalty, and legends.
We're hyped to have you with us!

✨ Make sure to:
🔹 Verify yourself in <#1401306747922284625>  (Required to unlock the server)
🔹 Read the rules in <#1396670355858391092>
🔹 Get your roles from <#1396726703564525688>
🔹 Say hi in <#1396801885322739743>

📣 Reminder: Be respectful, stay chill, and vibe with your fellow Royals.
Need help? Ping <@&1396679140303835278> <@&1396810929110388806>
Enjoy the music, games & chill vibes! 
Welcome again, Your Majesty! 🎈
━━━━━━━━━━━━━━━━━━━
https://cdn.discordapp.com/attachments/1338401226357870654/1410590875683127368/standard_3.gif?ex=68d48260&is=68d330e0&hm=bcc92770aa4fdbc5e8050d57652bd66e9f77628a78631aa74a69b46ceec86d03
"""

    await channel.send(welcome_message)

    # Autorole assignment (silent)
    role_id = autoroles.get(member.guild.id)
    if role_id:
        role = member.guild.get_role(role_id)
        if role:
            try:
                await member.add_roles(role)
            except:
                # Only notify if role assignment fails
                if channel:
                    await channel.send(f"❌ Cannot assign {role.mention} to {member.mention}, check my role hierarchy.")


# ---------- Role hierarchy check ----------
async def hierarchy_check(actor: discord.Member, target: discord.Member, interaction_or_ctx):
    if actor.top_role <= target.top_role:
        msg = f"❌ You cannot act on {target.mention}, their role is equal/higher."
        if isinstance(interaction_or_ctx, commands.Context):
            await interaction_or_ctx.send(msg)
        else:
            await interaction_or_ctx.response.send_message(msg, ephemeral=True)
        return False
    if interaction_or_ctx.guild.me.top_role <= target.top_role:
        msg = f"❌ I cannot act on {target.mention}, their role is higher than mine."
        if isinstance(interaction_or_ctx, commands.Context):
            await interaction_or_ctx.send(msg)
        else:
            await interaction_or_ctx.response.send_message(msg, ephemeral=True)
        return False
    return True

async def hierarchy_check(actor: discord.Member, target: discord.Member, ctx_or_interaction):
    """
    Check if actor can act on target based on role hierarchy and admin status.
    Prevents acting on server admins.
    """
    # Prevent acting on admins
    if target.guild_permissions.administrator:
        msg = f"❌ {target.mention} is an administrator and cannot be acted upon."
        if isinstance(ctx_or_interaction, commands.Context):
            await ctx_or_interaction.send(content=msg)
        else:
            await ctx_or_interaction.response.send_message(content=msg, ephemeral=False)
        return False

    # Normal role hierarchy check
    if actor.top_role <= target.top_role:
        msg = f"❌ You cannot act on {target.mention}, their role is equal/higher."
        if isinstance(ctx_or_interaction, commands.Context):
            await ctx_or_interaction.send(content=msg)
        else:
            await ctx_or_interaction.response.send_message(content=msg, ephemeral=False)
        return False
    if ctx_or_interaction.guild.me.top_role <= target.top_role:
        msg = f"❌ I cannot act on {target.mention}, their role is higher than mine."
        if isinstance(ctx_or_interaction, commands.Context):
            await ctx_or_interaction.send(content=msg)
        else:
            await ctx_or_interaction.response.send_message(content=msg, ephemeral=False)
        return False
    return True

# ---------- PREFIX COMMANDS ----------
@bot.command()
async def ping(ctx):
    await ctx.send(f"Pong! 🏓 Latency: {round(bot.latency*1000)}ms")

@bot.command()
@commands.has_permissions(manage_messages=True)
async def purge(ctx, amount: int):
    deleted = await ctx.channel.purge(limit=amount)
    await ctx.send(embed=mod_embed("Purge", f"Deleted {len(deleted)} messages."), delete_after=5)

@bot.command()
@commands.has_permissions(manage_roles=True)
async def addrole(ctx, member: discord.Member, role: discord.Role):
    if ctx.author.top_role <= role or ctx.guild.me.top_role <= role:
        return await ctx.send(f"❌ Cannot add {role.mention}, role too high.")
    await member.add_roles(role)
    await ctx.send(embed=mod_embed("Role Added", f"{role.mention} added to {member.mention}.", color=discord.Color.green()))

@bot.command()
@commands.has_permissions(manage_roles=True)
async def removerole(ctx, member: discord.Member, role: discord.Role):
    if ctx.author.top_role <= role or ctx.guild.me.top_role <= role:
        return await ctx.send(f"❌ Cannot remove {role.mention}, role too high.")
    await member.remove_roles(role)
    await ctx.send(embed=mod_embed("Role Removed", f"{role.mention} removed from {member.mention}.", color=discord.Color.orange()))

@bot.command()
@commands.has_permissions(manage_roles=True)
async def setautorole(ctx, role: discord.Role):
    autoroles[ctx.guild.id] = role.id
    await ctx.send(embed=mod_embed("Autorole Set", f"{role.mention} will be assigned to new members.", color=discord.Color.green()))

@bot.command()
@commands.has_permissions(manage_roles=True)
async def removeautorole(ctx):
    if ctx.guild.id in autoroles:
        del autoroles[ctx.guild.id]
        await ctx.send(embed=mod_embed("Autorole Removed", "Autorole removed.", color=discord.Color.orange()))
    else:
        await ctx.send("❌ No autorole is set.")

# ---------- SLASH COMMANDS ----------
# Ping
@bot.tree.command(name="ping", description="Check bot latency", guild=guild)
async def ping_slash(interaction: discord.Interaction):
    await interaction.response.send_message(f"Pong! 🏓 Latency: {round(bot.latency*1000)}ms")

# Announce
@bot.tree.command(name="announce", description="Send announcement", guild=guild)
@app_commands.describe(channel="Channel", message="Message")
async def announce_slash(interaction: discord.Interaction, channel: discord.TextChannel, message: str):
    if not interaction.user.guild_permissions.manage_messages:
        return await interaction.response.send_message("❌ No permission", ephemeral=True)
    await interaction.response.send_message(f"📢 Announcement sent to {channel.mention}", ephemeral=True)
    await channel.send(f"{message}")

# Purge
@bot.tree.command(name="purge", description="Delete messages", guild=guild)
@app_commands.describe(amount="Number of messages to delete")
async def purge_slash(interaction: discord.Interaction, amount: int):
    if not interaction.user.guild_permissions.manage_messages:
        return await interaction.response.send_message("❌ No permission", ephemeral=True)
    await interaction.response.defer(ephemeral=True)
    deleted = await interaction.channel.purge(limit=amount)
    await interaction.followup.send(embed=mod_embed("Purge", f"Deleted {len(deleted)} messages."))

# AddRole
@bot.tree.command(name="addrole", description="Add role to member", guild=guild)
@app_commands.describe(member="Member", role="Role to add")
async def addrole_slash(interaction: discord.Interaction, member: discord.Member, role: discord.Role):
    if not interaction.user.guild_permissions.manage_roles:
        return await interaction.response.send_message("❌ No permission", ephemeral=True)
    if interaction.user.top_role <= role or interaction.guild.me.top_role <= role:
        return await interaction.response.send_message(f"❌ Cannot add {role.mention}, role too high.", ephemeral=True)
    await interaction.response.defer(ephemeral=True)
    await member.add_roles(role)
    await interaction.followup.send(embed=mod_embed("Role Added", f"{role.mention} added to {member.mention}.", color=discord.Color.green()))

# RemoveRole
@bot.tree.command(name="removerole", description="Remove role from member", guild=guild)
@app_commands.describe(member="Member", role="Role to remove")
async def removerole_slash(interaction: discord.Interaction, member: discord.Member, role: discord.Role):
    if not interaction.user.guild_permissions.manage_roles:
        return await interaction.response.send_message("❌ No permission", ephemeral=True)
    if interaction.user.top_role <= role or interaction.guild.me.top_role <= role:
        return await interaction.response.send_message(f"❌ Cannot remove {role.mention}, role too high.", ephemeral=True)
    await interaction.response.defer(ephemeral=True)
    await member.remove_roles(role)
    await interaction.followup.send(embed=mod_embed("Role Removed", f"{role.mention} removed from {member.mention}.", color=discord.Color.orange()))

# Autorole slash
@bot.tree.command(name="setautorole", description="Set autorole for new members", guild=guild)
@app_commands.describe(role="Role to assign automatically")
async def setautorole_slash(interaction: discord.Interaction, role: discord.Role):
    if not interaction.user.guild_permissions.manage_roles:
        return await interaction.response.send_message("❌ No permission", ephemeral=True)
    autoroles[interaction.guild.id] = role.id
    await interaction.response.send_message(embed=mod_embed("Autorole Set", f"{role.mention} will be assigned to new members.", color=discord.Color.green()))

@bot.tree.command(name="removeautorole", description="Remove autorole", guild=guild)
async def removeautorole_slash(interaction: discord.Interaction):
    if not interaction.user.guild_permissions.manage_roles:
        return await interaction.response.send_message("❌ No permission", ephemeral=True)
    if interaction.guild.id in autoroles:
        del autoroles[interaction.guild.id]
        await interaction.response.send_message(embed=mod_embed("Autorole Removed", "Autorole removed.", color=discord.Color.orange()))
    else:
        await interaction.response.send_message("❌ No autorole is set.", ephemeral=True)

# ---------- MOD COMMANDS ----------



@bot.command()
async def serverinfo(ctx):
    guild = ctx.guild
    embed = discord.Embed(title=f"{guild.name} Info", color=discord.Color.blue())
    embed.set_thumbnail(url=guild.icon.url if guild.icon else None)
    embed.add_field(name="Server ID", value=guild.id, inline=True)
    embed.add_field(name="Owner", value=guild.owner, inline=True)
    embed.add_field(name="Members", value=guild.member_count, inline=True)
    embed.add_field(name="Roles", value=len(guild.roles), inline=True)
    embed.add_field(name="Text Channels", value=len(guild.text_channels), inline=True)
    embed.add_field(name="Voice Channels", value=len(guild.voice_channels), inline=True)
    embed.add_field(name="Boosts", value=guild.premium_subscription_count, inline=True)
    await ctx.send(embed=embed)

@bot.command()
@commands.has_permissions(administrator=True)
async def memberinfo(ctx, member: discord.Member = None):
    member = member or ctx.author
    embed = discord.Embed(title=f"{member} Info", color=discord.Color.green())
    embed.set_thumbnail(url=member.display_avatar.url)
    embed.add_field(name="ID", value=member.id, inline=True)
    embed.add_field(name="Bot", value=member.bot, inline=True)
    embed.add_field(name="Top Role", value=member.top_role.mention, inline=True)
    embed.add_field(name="Joined Server", value=member.joined_at.strftime("%d %b %Y %H:%M:%S"), inline=True)
    embed.add_field(name="Account Created", value=member.created_at.strftime("%d %b %Y %H:%M:%S"), inline=True)
    roles = [r.mention for r in member.roles if r != ctx.guild.default_role]
    embed.add_field(name="Roles", value=", ".join(roles) if roles else "None", inline=False)
    await ctx.send(embed=embed)

@bot.command()
@commands.has_permissions(administrator=True)
async def roleinfo(ctx, role: discord.Role):
    embed = discord.Embed(title=f"{role.name} Info", color=role.color)
    embed.add_field(name="Role ID", value=role.id)
    embed.add_field(name="Position", value=role.position)
    embed.add_field(name="Mentionable", value=role.mentionable)
    embed.add_field(name="Hoisted", value=role.hoist)
    embed.add_field(name="Members with Role", value=len(role.members))
    await ctx.send(embed=embed)

@bot.command()
async def avatar(ctx, member: discord.Member = None):
    member = member or ctx.author
    embed = discord.Embed(title=f"{member}'s Avatar", color=discord.Color.purple())
    embed.set_image(url=member.display_avatar.url)
    await ctx.send(embed=embed)

# ---------- SLASH COMMANDS ----------

@bot.tree.command(name="serverinfo", description="Show server information", guild=guild)
async def serverinfo_slash(interaction: discord.Interaction):
    guild = interaction.guild
    embed = discord.Embed(title=f"{guild.name} Info", color=discord.Color.blue())
    embed.set_thumbnail(url=guild.icon.url if guild.icon else None)
    embed.add_field(name="Server ID", value=guild.id, inline=True)
    embed.add_field(name="Owner", value=guild.owner, inline=True)
    embed.add_field(name="Members", value=guild.member_count, inline=True)
    embed.add_field(name="Roles", value=len(guild.roles), inline=True)
    embed.add_field(name="Text Channels", value=len(guild.text_channels), inline=True)
    embed.add_field(name="Voice Channels", value=len(guild.voice_channels), inline=True)
    embed.add_field(name="Boosts", value=guild.premium_subscription_count, inline=True)
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="memberinfo", description="Show member information (Admins only)", guild=guild)
@app_commands.describe(member="Select member")
async def memberinfo_slash(interaction: discord.Interaction, member: discord.Member = None):
    if not interaction.user.guild_permissions.administrator:
        return await interaction.response.send_message("❌ Admins only", ephemeral=True)
    member = member or interaction.user
    embed = discord.Embed(title=f"{member} Info", color=discord.Color.green())
    embed.set_thumbnail(url=member.display_avatar.url)
    embed.add_field(name="ID", value=member.id, inline=True)
    embed.add_field(name="Bot", value=member.bot, inline=True)
    embed.add_field(name="Top Role", value=member.top_role.mention, inline=True)
    embed.add_field(name="Joined Server", value=member.joined_at.strftime("%d %b %Y %H:%M:%S"), inline=True)
    embed.add_field(name="Account Created", value=member.created_at.strftime("%d %b %Y %H:%M:%S"), inline=True)
    roles = [r.mention for r in member.roles if r != interaction.guild.default_role]
    embed.add_field(name="Roles", value=", ".join(roles) if roles else "None", inline=False)
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="roleinfo", description="Show role information (Admins only)", guild=guild)
@app_commands.describe(role="Select role")
async def roleinfo_slash(interaction: discord.Interaction, role: discord.Role):
    if not interaction.user.guild_permissions.administrator:
        return await interaction.response.send_message("❌ Admins only", ephemeral=True)
    embed = discord.Embed(title=f"{role.name} Info", color=role.color)
    embed.add_field(name="Role ID", value=role.id)
    embed.add_field(name="Position", value=role.position)
    embed.add_field(name="Mentionable", value=role.mentionable)
    embed.add_field(name="Hoisted", value=role.hoist)
    embed.add_field(name="Members with Role", value=len(role.members))
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="avatar", description="Show a member's avatar", guild=guild)
@app_commands.describe(member="Select member")
async def avatar_slash(interaction: discord.Interaction, member: discord.Member = None):
    member = member or interaction.user
    embed = discord.Embed(title=f"{member}'s Avatar", color=discord.Color.purple())
    embed.set_image(url=member.display_avatar.url)
    await interaction.response.send_message(embed=embed)


# ----------------- HELP COMMAND WITH BUTTONS -----------------
class HelpView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Moderation", style=discord.ButtonStyle.red, emoji="🛠️")
    async def moderation(self, interaction: discord.Interaction, button: discord.ui.Button):
        embed = discord.Embed(title="Moderation Commands", color=discord.Color.red())
        embed.add_field(name="/ban", value="Ban a member", inline=False)
        embed.add_field(name="/unban", value="Unban a member", inline=False)
        embed.add_field(name="/kick", value="Kick a member", inline=False)
        embed.add_field(name="/timeban", value="Temporarily ban a member", inline=False)
        embed.add_field(name="/purge", value="Delete multiple messages", inline=False)
        await interaction.response.edit_message(embed=embed, view=self)

    @discord.ui.button(label="Utility", style=discord.ButtonStyle.blurple, emoji="🧰")
    async def utility(self, interaction: discord.Interaction, button: discord.ui.Button):
        embed = discord.Embed(title="Utility Commands", color=discord.Color.blue())
        embed.add_field(name="/serverinfo", value="Server information", inline=False)
        embed.add_field(name="/memberinfo", value="Member information", inline=False)
        embed.add_field(name="/roleinfo", value="Role information", inline=False)
        embed.add_field(name="/avatar", value="Get user's avatar", inline=False)
        embed.add_field(name="/announce", value="Send an announcement", inline=False)
        await interaction.response.edit_message(embed=embed, view=self)

    @discord.ui.button(label="Fun", style=discord.ButtonStyle.green, emoji="🎉")
    async def fun(self, interaction: discord.Interaction, button: discord.ui.Button):
        embed = discord.Embed(title="Fun Commands", color=discord.Color.green())
        embed.add_field(name="/roast", value="Roast a member", inline=False)
        embed.add_field(name="/joke", value="Tell a joke", inline=False)
        await interaction.response.edit_message(embed=embed, view=self)

# ----------------- SLASH COMMAND -----------------
@bot.tree.command(name="help", description="Show all bot commands", guild=guild)
async def help_command(interaction: discord.Interaction):
    embed = discord.Embed(title="Bot Commands", description="Select a category using the buttons below!", color=discord.Color.gold())
    view = HelpView()
    await interaction.response.send_message(embed=embed, view=view, ephemeral=True)

# ----------------- PREFIX COMMAND (Optional) -----------------
@bot.command()
async def help(ctx):
    embed = discord.Embed(title="Bot Commands", description="Use the buttons below to navigate through commands!", color=discord.Color.gold())
    view = HelpView()
    await ctx.send(embed=embed, view=view)


import random

roasts = [
    "You're as useless as the 'ueue' in 'queue'.",
    "I'd agree with you but then we'd both be wrong.",
    "You're like a cloud. When you disappear, it's a beautiful day.",
    "You have the charm of a funeral and the personality of mildew.",
    "If ignorance is bliss, you must be ecstasy.",
    "You're the reason the gene pool needs a lifeguard.",
    "Your soul called—it wants to unsubscribe.",
    "You're like a cloud—when you disappear, it's a beautiful day.",
    "You have the charisma of wet cardboard.",
    "You couldn't pour water out of a boot if the instructions were inside.",
    "You're proof evolution can take a few steps back.",
    "Calling you stupid would be an insult to stupid people.",
    "Your birth certificate is an apology from the universe.",
    "You bring new meaning to 'forgettable.'",
    "You have the warmth of a black hole.",
    "Your brain is a loading screen that never finishes.",
    "You're a human typo in the story of life.",
    "Your presence is like static on a dead TV channel.",
    "You're the human equivalent of spam in an inbox.",
    "You have the personality of decaf coffee.",
    "You're like a mosquito bite in winter—completely unnecessary.",
    "Your soul is like burnt toast—bitter and dry.",
    "You have the subtlety of a chainsaw in a library.",
    "You're living proof mistakes can multiply.",
    "You're like a flat soda—disappointing and sad.",
    "You have all the elegance of a stumbling giraffe.",
    "Your aura screams 'I peaked in middle school.'",
    "You're a cautionary tale in human form.",
    "Your voice is the sound of nails on a chalkboard—eternal.",
    "You're the appendix of humanity—nobody knows why you exist.",
    "You're a human pothole—painful to encounter.",
    "Your life is the beta version nobody wanted to test.",
    "You're like expired milk—every word you say stinks.",
    "Your thoughts are as empty as your social calendar.",
    "You have the emotional range of soggy pasta.",
    "You're a glitch in the simulation of life.",
    "Your existence is the result of a cosmic typo.",
    "You're the human equivalent of a participation trophy.",
    "You have the appeal of a wet mop.",
    "You're like a broken pencil—completely pointless.",
    "Your aura smells like regret and mildew.",
    "You're the human version of a software bug.",
    "Your presence ruins the room faster than a fart in an elevator.",
    "You're like decaf energy—completely ineffective.",
    "Your personality is the wallpaper of boredom.",
    "You're living proof that some mistakes multiply exponentially.",
    "You have the impact of a gentle sigh in a hurricane.",
    "You're like cold soup: nobody wants you, but someone pretends to care.",
    "Your brain operates on airplane mode—permanently.",
    "You're the human embodiment of a '404 Not Found'.",
    "You have the social skills of spam email.",
    "You're like a broken mirror: everything you touch is distorted.",
    "Your presence is the definition of 'unwanted attention.'",
    "You're a human hiccup in the rhythm of life.",
    "You have the allure of expired milk.",
    "You're a cautionary tale of bad decisions in motion.",
    "Your life is like a loading screen nobody waits for.",
    "You have the subtlety of a brick to the shin.",
    "You're the plot twist nobody asked for.",
    "Your existence is a typo the universe regrets.",
    "You're like decaf coffee: pointless and disappointing.",
    "You have the charisma of a dial tone.",
    "You're living proof that monotony can be a personality trait.",
    "You have the soul of a forgotten password.",
    "You're a glitch nobody wants to fix.",
    "Your impact is weaker than a soggy firecracker.",
    "You're a black hole of fun, joy, and hope.",
    "You have the originality of a photocopy.",
    "You're a human error nobody can undo.",
    "Your life story is a cautionary tale written in bad font.",
    "You're like a cloud of mosquitoes: annoying and disposable.",
    "You bring the term 'irrelevant' to life.",
    "You're the human version of a participation ribbon.",
    "You have the warmth of an abandoned freezer.",
    "You're proof some things shouldn’t exist.",
    "Your existence is like a typo in evolution’s manuscript.",
    "You have the subtlety of a chainsaw in a teacup.",
    "You're like a broken alarm clock: useless and annoying.",
    "Your soul is the black mold of humanity.",
    "You’re the human equivalent of spam calls.",
    "You have the allure of a parking ticket.",
    "You're like a flat tire—completely useless and inconvenient.",
    "Your thoughts are as expired as last year’s milk.",
    "You're a cautionary tale in human form.",
    "You bring new meaning to 'pointless'.",
    "You're the human version of a software crash.",
    "Your personality could stop a clock—permanently.",
    "You're a walking plot hole.",
    "You have the elegance of a chicken on roller skates.",
    "You're like a mosquito buzzing in an empty cave.",
    "Your life is the beta version of a failed experiment.",
    "You're like cold oatmeal—bland, sad, and wet.",
    "You have the moral compass of a drunken raccoon.",
    "You're a human hiccup nobody wants to hear.",
    "Your aura screams 'existential disappointment'.",
    "You're like a fax machine in 2025—completely irrelevant.",
    "Your voice has all the warmth of a car horn.",
    "You're the appendix nobody needed.",
    "You’re a glitch nobody wants to debug.",
    "You have all the subtlety of a hurricane in a library.",
    "You're like spoiled milk in a recipe—ruining everything.",
    "Your personality is a black-and-white TV in a 4K world.",
    "You have the emotional depth of a puddle.",
    "You're a human hiccup in the rhythm of life.",
    "Your presence is like static nobody asked for.",
    "You have the charisma of a wet mop.",
    "You're the human equivalent of a broken pencil—pointless.",
    "Your life is a cautionary tale nobody wants to read.",
    "You're proof that even mistakes can make mistakes.",
    "You have the impact of a soggy firecracker."
    "You’re the human version of a participation award no one asked for.",
    "Your mind is a haunted house: full of ghosts, but nothing inside.",
    "You’re the leftover food of human evolution—inedible and sad.",
    "Your personality is a speed bump in the highway of life.",
    "You’re the embodiment of Monday mornings—nobody likes you.",
    "Your existence is the plot twist nobody wanted.",
    "You’re like a black hole—sucking the fun out of everything.",
    "Your thoughts are like dial-up internet—slow and outdated.",
    "You’re a human fog: nobody sees you, nobody wants you.",
    "You have the social skills of a malfunctioning vending machine.",
    "You’re the typo in the story of humanity.",
    "Your aura smells like regret and expired milk.",
    "You’re proof some mistakes can’t be undone.",
    "You’re like a wet sock in winter—cold and miserable.",
    "Your personality is as dry as a desert graveyard.",
    "You’re the human equivalent of a dull knife—useless and dangerous.",
    "Your life is like a software update—nobody asked, and everything breaks.",
    "You have all the charm of a tax audit.",
    "You’re like a mosquito in a cave—nobody cares.",
    "Your existence is the universe’s apology for something else.",
    "You’re a punctuation error in the book of life.",
    "Your impact is like a candle in a hurricane—gone instantly.",
    "You have the allure of spoiled milk left in the sun.",
    "You’re the human version of a speed bump in a racetrack.",
    "Your brain is like a broken compass—always pointing nowhere.",
    "You’re a glitch in reality that nobody wants to fix.",
    "Your life is a beta test nobody signed up for.",
    "You’re like a broken mirror—everything you touch is distorted.",
    "Your personality is the definition of bland.",
    "You’re a cautionary tale with a sad soundtrack.",
    "Your soul is a flat tire—nobody wants to inflate it.",
    "You have the elegance of a flailing octopus.",
    "You’re proof that entropy can be personified.",
    "Your thoughts are like smoke—everywhere and useless.",
    "You’re the human equivalent of static noise.",
    "Your aura is the black mold of humanity.",
    "You have the charisma of a wet mop in a hurricane.",
    "You’re like a cloudy day that never ends.",
    "Your presence makes elevators awkward and silent.",
    "You’re the human version of spam calls—annoying and pointless.",
    "Your life is a bug nobody can patch.",
    "You have the subtlety of a fire alarm in a library.",
    "You’re the appendix of society—nobody notices until it hurts.",
    "Your personality is like a dead battery—completely powerless.",
    "You’re a human hiccup nobody asked for.",
    "Your existence is the cosmic equivalent of a typo.",
    "You have the warmth of a morgue.",
    "You’re proof that mediocrity can be personified.",
    "Your life is the footnote nobody reads.",
    "You’re like decaf coffee—promises energy, delivers nothing.",
    "Your mind is a broken GPS—always lost.",
    "You have the social presence of a wet paper bag.",
    "You’re a human pothole—painful to encounter.",
    "Your personality is a flat soda—disappointing and sad.",
    "You’re like a fax machine in the era of smartphones.",
    "Your aura screams 'existential failure.'",
    "You’re proof that entropy is contagious.",
    "Your thoughts are like expired coupons—useless and discarded.",
    "You’re a glitch in the matrix of life.",
    "Your presence is the human version of a typo.",
    "You have the subtlety of a jackhammer in a cathedral.",
    "You’re the leftover sadness from someone else’s life.",
    "Your brain is the Windows 95 of intelligence.",
    "You’re a human participation ribbon—cheap and meaningless.",
    "Your personality is a black-and-white TV in a 4K world.",
    "You’re the caution sign nobody follows.",
    "Your life is a trial nobody signed up for.",
    "You have the emotional range of a soggy noodle.",
    "You’re the human equivalent of spam email.",
    "Your aura smells like regret and mildew.",
    "You’re proof that bad ideas can reproduce.",
    "Your existence is a cosmic joke with no punchline.",
    "You have the charisma of cold oatmeal.",
    "You’re the human equivalent of a broken pencil—pointless.",
    "Your thoughts are as empty as a forgotten password.",
    "You’re a cautionary tale in high definition.",
    "Your presence is like a mosquito buzzing in a cave—irrelevant.",
    "You have the grace of a pigeon in a hurricane.",
    "You’re a walking plot hole in the story of life.",
    "Your soul is like burnt toast—bitter and dry.",
    "You’re a glitch nobody wants to debug.",
    "Your life is like a participation award at a funeral.",
    "You have all the subtlety of a brick to the shin.",
    "You’re the human version of decayed leftovers.",
    "Your personality is as inspiring as a traffic cone.",
    "You’re the human equivalent of a broken alarm clock.",
    "Your impact is weaker than a soggy firecracker.",
    "You have the elegance of a stumbling giraffe.",
    "You’re the human equivalent of spam in a group chat.",
    "Your existence is a cosmic typo nobody can delete.",
    "You’re proof that mediocrity can reproduce exponentially.",
    "Your aura is the black hole of enthusiasm.",
    "You’re a cautionary tale with no moral.",
    "Your life is like a loading screen nobody waits for.",
    "You have the appeal of a wet mop.",
    "You’re the human equivalent of a dull knife—useless and dangerous.",
    "Your personality could stop a clock permanently.",
    "You’re like expired milk—everywhere you go, it stinks.",
    "Your brain operates on airplane mode—permanently.",
    "You’re a glitch in reality that no one wants to fix.",
    "Your thoughts are like smoke—everywhere, nowhere, useless.",
    "You have the warmth of an abandoned freezer."

]

self_roasts = [
    "Roasting yourself? That takes courage... or stupidity!",
    "Ah, hitting yourself, I see. Good luck with that.",
    "Self-roast activated: you still can't fix your mistakes!"
]

@bot.tree.command(name="roast", description="Roast a member", guild=guild)
@app_commands.describe(member="Member to roast")
async def roast_slash(interaction: discord.Interaction, member: discord.Member = None):
    target = member or interaction.user

    if target == interaction.user:
        roast = random.choice(self_roasts)
    else:
        roast = random.choice(roasts)

    await interaction.response.send_message(f"{target.mention} 🔥 {roast}")

@bot.command(name="roast")
async def roast_prefix(ctx, member: discord.Member = None):
    target = member or ctx.author

    if target == ctx.author:
        roast = random.choice(self_roasts)
    else:
        roast = random.choice(roasts)

    await ctx.send(f"{target.mention} 🔥 {roast}")



jokes = [
    "Why don't scientists trust atoms? Because they make up everything!",
    "Why did the scarecrow win an award? Because he was outstanding in his field!",
    "I told my computer I needed a break, and it said 'No problem — I'll go to sleep.'",
    "Why do cows have hooves instead of feet? Because they lactose.",
    "Why don’t skeletons fight each other? They don’t have the guts.",
    "I told my computer I needed a break, and it said 'Error 404: Coffee not found.'",
    "Why don’t graveyards ever get overcrowded? People are dying to get in.",
    "I asked the librarian if books about paranoia were available. She whispered, 'They’re right behind you.'",
    "Why did the scarecrow win an award? Because he was outstanding in his field.",
    "Why did the zombie go to school? He wanted to improve his 'dead'ucation.",
    "I would tell you a joke about time travel, but you didn’t like it.",
    "Why did the vampire get hired as a banker? He was good at counting bloods.",
    "Parallel lines have so much in common… it’s a shame they’ll never meet.",
    "Why did the ghost go to the party? Because he had no body to go with.",
    "I told my therapist about my obsession with revenge… now he’s obsessed with avoiding me.",
    "Why don’t cannibals eat clowns? They taste funny.",
    "I ate a clock yesterday. It was very time-consuming.",
    "Why did the chicken cross the playground? To get to the other slide.",
    "I have a joke about construction… but I’m still working on it.",
    "Why did the picture go to jail? Because it was framed.",
    "I asked a skeleton for a loan… but he had no body to co-sign.",
    "Why did the coffee file a police report? It got mugged.",
    "I told a dead baby joke once… it didn’t go over well.",
    "Why don’t mummies take vacations? They’re afraid they’ll relax and unwind.",
    "I have a joke about unemployment… but no one’s working right now.",
    "Why did the math book look sad? It had too many problems.",
    "Why was the broom late? It swept in.",
    "I tried to write a dark joke, but it died on the page.",
    "Why did the vampire flunk art class? He could only draw blood.",
    "I have a joke about amnesia… but I forgot it.",
    "Why don’t graveyards ever get lonely? People are dying to be there.",
    "I wanted to make a joke about horror movies… it scared me first.",
    "Why did the chicken join a band? Because it had the drumsticks.",
    "I would tell a joke about infinity, but it would never end.",
    "Why did Dracula become a vegetarian? Because biting necks was a pain in the neck.",
    "I told my ghost roommate to clean up… now he’s haunting the trash.",
    "Why did the skeleton go to the party alone? He had no body to go with.",
    "I have a joke about black holes… it sucks the life out of everyone.",
    "Why did the zombie go to therapy? He felt dead inside.",
    "I wanted to tell a chemistry joke, but all the good ones argon.",
    "Why did the vampire get promoted? He was fang-tastic at his job.",
    "I tried to tell a joke about AI, but it became self-aware and left.",
    "Why do graveyards make great comedians? They know all the best deadpan jokes.",
    "I have a joke about cannibalism… but it’s too hard to digest.",
    "Why did the skeleton refuse to fight? He didn’t have the guts.",
    "I told my fridge a joke… now it’s chill.",
    "Why did the monster sit in the corner? He felt a little Frankenstein.",
    "I have a joke about haunted houses… but it’ll raise your spirits.",
    "Why did the vampire read newspapers? He liked current events.",
    "I wanted to make a joke about a serial killer… but it was cut short.",
    "Why did the ghost go to therapy? He needed to let things go.",
    "I told my graveyard a joke… it died laughing.",
    "Why did the scarecrow get promoted? He was outstanding in his field.",
    "I have a joke about coffins… it’s a real sleeper hit.",
    "Why don’t mummies like parties? They get too wrapped up in them.",
    "I tried to tell a pun about corpses… but it was dead on arrival.",
    "Why did the skeleton call in sick? He was bone tired.",
    "I have a joke about cremation… it’s a burning issue.",
    "Why did the vampire go to art class? He wanted to draw blood.",
    "I wanted to tell a joke about grave robbers… but it was in poor taste.",
    "Why did the zombie break up with his girlfriend? She didn’t have the guts either.",
    "I have a joke about monsters… but it’s scary good.",
    "Why did the skeleton avoid the party? He had no body to go with.",
    "I tried to make a pun about ghosts… it’s spiritless.",
    "Why did Dracula read so much? He wanted to improve his 'blood'line.",
    "I have a joke about curses… it’s hex-tra funny.",
    "Why did the coffin start a band? It wanted to rock the dead.",
    "I told a joke about vampires… it was a pain in the neck.",
    "Why did the haunted house apply for insurance? It had too many claims.",
    "I have a joke about werewolves… it’s a howling success.",
    "Why did the ghost get promoted? He was really good at raising spirits.",
    "I wanted to make a joke about zombies… but it had no bite.",
    "Why did the skeleton go to school? To bone up on knowledge.",
    "I have a joke about graveyards… it’s a dead giveaway.",
    "Why did the vampire start a blog? He had too many biting comments.",
    "I tried to make a joke about witches… it was spell-binding.",
    "Why did the mummy go to the doctor? He was all wrapped up in problems.",
    "I have a joke about crypts… it’s underground humor.",
    "Why did the ghost sit in the corner? He felt a little transparent.",
    "I wanted to tell a joke about devils… but it’s hellishly hard.",
    "Why did the skeleton go on a diet? He wanted to keep his bones light.",
    "I have a joke about poltergeists… it’ll knock you out.",
    "Why did the zombie go to school? To improve his 'dead'ucation.",
    "I tried to tell a vampire joke… but it went over their head.",
    "Why did the ghost cross the road? To get to the other sigh.",
    "I have a joke about grave robbers… it’s a real dig.",
    "Why did the vampire avoid garlic? He couldn’t handle the bite.",
    "I wanted to tell a ghost joke… but it vanished.",
    "Why did the skeleton go to the dance? To shake a leg.",
    "I have a joke about witches… it’s magically funny.",
    "Why did the zombie go to the party? He was dying for some fun.",
    "I tried to tell a pun about haunted houses… it scared everyone.",
    "Why did the vampire stay in bed? He was coffin.",
    "I have a joke about coffins… it’s a grave matter.",
    "Why did the ghost go to the doctor? He needed a little spirit lift.",
    "I wanted to make a joke about werewolves… it’s fur-midable.",
    "Why did the skeleton go to the barbecue? To get another rib.",
    "I have a joke about zombies… it’s dead funny.",
    "Why did the ghost join the choir? He had a haunting voice.",
    "I tried to make a vampire joke… it sucked.",
    "Why did the mummy go to the library? To unwind.",
    "I have a joke about haunted dolls… it’s doll-iciously scary.",
    "Why did the vampire go to the dentist? To improve his bite.",
    "I wanted to tell a skeleton joke… it was humerus.",
    "Why did the ghost break up with his girlfriend? She didn’t have spirit.",
    "I have a joke about witches… it’s brooming with laughter.",
    "Why did the zombie go jogging? He wanted to work on his dead-lift.",
    "I tried to make a pun about vampires… it was fang-tastic.",
    "Why did the skeleton fail art class? He couldn’t draw blood.",
    "I have a joke about poltergeists… it’ll haunt you.",
    "Why did the ghost sit in the library? He wanted to read between the sheets.",
    "I wanted to tell a joke about monsters… it’s monstrous.",
    "Why did the zombie start a YouTube channel? He wanted to go viral.",
    "I have a joke about haunted mirrors… it reflects poorly.",
    "Why did the vampire avoid the sun? He didn’t want a sunburned neck.",
    "I tried to make a pun about skeletons… it was bone-chilling.",
    "Why did the ghost apply for a job? He needed some spirit income.",
    "I have a joke about witches’ cats… it’s purr-fectly evil.",
    "Why did the zombie sit quietly? He was dead tired.",
    "I wanted to tell a ghost joke… but it passed through everyone.",
    "Why did the skeleton go to the party? To shake things up.",
    "I have a joke about vampires… it’s to die for.",
    "Why did the haunted house become famous? It had a lot of fans.",
    "I tried to tell a pun about zombies… it was bite-sized humor.",
    "Why did the ghost fail math class? He kept disappearing from problems.",
    "I have a joke about crypts… it’s a tomb of laughs.",
    "Why did the vampire go to school? He wanted to brush up on his history of blood.",
    "I wanted to tell a skeleton joke… it was rib-tickling.",
    "Why did the zombie go on vacation? He needed a change of grave scenery.",
    "I have a joke about haunted forests… it’s tree-mendously spooky.",
    "Why did the mummy take a break? He was all wrapped up in work.",
    "I tried to make a pun about vampires… it drained my energy.",
    "Why did the skeleton hate winter? He couldn’t feel his bones.",
    "I have a joke about ghosts… it’s spirited humor.",
    "Why did the zombie fail the driving test? He kept hitting pedestrians.",
    "I wanted to tell a haunted castle joke… it’s wall-to-wall funny.",
    "Why did the vampire avoid mirrors? He didn’t want to reflect on his life.",
    "I have a joke about skeletons at the gym… they do exorcise.",
    "Why did the ghost go to school? To improve his haunting skills.",
    "I tried to tell a vampire pun… it was fang-tastic.",
    "Why did the haunted house go to therapy? Too many skeletons in the closet.",
    "I have a joke about zombies… it’s dead serious humor.",
    "Why did the skeleton sit on the porch? He was feeling bone-ly.",
    "I wanted to tell a pun about coffins… it’s a grave topic.",
    "Why did the ghost join the band? He had the spirit."
]

async def tell_joke(ctx_or_interaction):
    joke = random.choice(jokes)
    
    if isinstance(ctx_or_interaction, discord.Interaction):
        await ctx_or_interaction.response.send_message(joke)
    else:
        await ctx_or_interaction.send(joke)

@bot.tree.command(name="joke", description="Tell a random joke", guild=guild)
async def joke_slash(interaction: discord.Interaction):
    await tell_joke(interaction)


@bot.command()
async def joke(ctx):
    await tell_joke(ctx)

# ---------------- MODERATION COMMANDS ----------------
# --------------- BAN ----------------
async def ban_action(target, reason, ctx_or_interaction):
    if not await hierarchy_check(ctx_or_interaction.user if isinstance(ctx_or_interaction, discord.Interaction) else ctx_or_interaction.author, target, ctx_or_interaction):
        return
    try:
        await target.send(f"⚠️ You were banned from {ctx_or_interaction.guild.name}\nReason: {reason}")
    except: pass
    await target.ban(reason=reason)
    embed = discord.Embed(title="Member Banned", 
                          description=f"{target.mention} has been banned\nReason: {reason}", color=discord.Color.dark_red())
    await send_response(ctx_or_interaction, embed=embed)
    # Announce publicly
    announce_channel = ctx_or_interaction.guild.get_channel(MOD_CHANNEL)
    if announce_channel:
        await announce_channel.send(embed=embed)

# Prefix
@bot.command(name="ban")
@commands.has_permissions(ban_members=True)
async def ban_prefix(ctx, member: discord.Member, *, reason: str="No reason provided"):
    await ban_action(member, reason, ctx)

# Slash
@bot.tree.command(name="ban", description="Ban a member", guild=guild)
@app_commands.describe(member="Member to ban", reason="Reason for ban")
async def ban_slash(interaction: discord.Interaction, member: discord.Member, reason: str="No reason provided"):
    if not interaction.user.guild_permissions.ban_members:
        return await interaction.response.send_message("❌ No permission", ephemeral=False)
    await interaction.response.defer(ephemeral=False)
    await ban_action(member, reason, interaction)


# --------------- KICK ----------------
async def kick_action(target, reason, ctx_or_interaction):
    if not await hierarchy_check(ctx_or_interaction.user if isinstance(ctx_or_interaction, discord.Interaction) else ctx_or_interaction.author, target, ctx_or_interaction):
        return
    try:
        await target.send(f"⚠️ You were kicked from {ctx_or_interaction.guild.name}\nReason: {reason}")
    except: pass
    await target.kick(reason=reason)
    embed = discord.Embed(title="Member Kicked", 
                          description=f"{target.mention} has been kicked\nReason: {reason}", color=discord.Color.dark_orange())
    await send_response(ctx_or_interaction, embed=embed)
    # Announce publicly
    announce_channel = ctx_or_interaction.guild.get_channel(MOD_CHANNEL)
    if announce_channel:
        await announce_channel.send(embed=embed)

# Prefix
@bot.command(name="kick")
@commands.has_permissions(kick_members=True)
async def kick_prefix(ctx, member: discord.Member, *, reason: str="No reason provided"):
    await kick_action(member, reason, ctx)

# Slash
@bot.tree.command(name="kick", description="Kick a member", guild=guild)
@app_commands.describe(member="Member to kick", reason="Reason for kick")
async def kick_slash(interaction: discord.Interaction, member: discord.Member, reason: str="No reason provided"):
    if not interaction.user.guild_permissions.kick_members:
        return await interaction.response.send_message("❌ No permission", ephemeral=False)
    await interaction.response.defer(ephemeral=False)
    await kick_action(member, reason, interaction)


# --------------- TIMEBAN ----------------
async def timeban_action(target, duration_hours, reason, ctx_or_interaction):
    if not await hierarchy_check(ctx_or_interaction.user if isinstance(ctx_or_interaction, discord.Interaction) else ctx_or_interaction.author, target, ctx_or_interaction):
        return
    try:
        await target.send(f"⚠️ You were temporarily banned from {ctx_or_interaction.guild.name} for {duration_hours}h\nReason: {reason}")
    except: pass
    await target.ban(reason=reason)
    embed = discord.Embed(title="Temporary Ban", 
                          description=f"{target.mention} has been banned for {duration_hours} hours\nReason: {reason}", color=discord.Color.dark_red())
    await send_response(ctx_or_interaction, embed=embed)
    announce_channel = ctx_or_interaction.guild.get_channel(MOD_CHANNEL)
    if announce_channel:
        await announce_channel.send(embed=embed)
    await asyncio.sleep(duration_hours * 3600)
    try:
        await ctx_or_interaction.guild.unban(target)
        unban_embed = discord.Embed(title="Temporary Ban Lifted", 
                                    description=f"{target.mention} has been unbanned after {duration_hours} hours", color=discord.Color.green())
        if announce_channel:
            await announce_channel.send(embed=unban_embed)
    except: pass

# Prefix
@bot.command(name="timeban")
@commands.has_permissions(ban_members=True)
async def timeban_prefix(ctx, member: discord.Member, duration_hours: float, *, reason: str="No reason provided"):
    await timeban_action(member, duration_hours, reason, ctx)

# Slash
@bot.tree.command(name="timeban", description="Temporarily ban a member", guild=guild)
@app_commands.describe(member="Member to ban", duration_hours="Hours", reason="Reason")
async def timeban_slash(interaction: discord.Interaction, member: discord.Member, duration_hours: float, reason: str="No reason provided"):
    if not interaction.user.guild_permissions.ban_members:
        return await interaction.response.send_message("❌ No permission", ephemeral=False)
    await interaction.response.defer(ephemeral=False)
    await timeban_action(member, duration_hours, reason, interaction)


# --------------- UNBAN ----------------
async def unban_action(user_id, ctx_or_interaction):
    user = await bot.fetch_user(int(user_id))
    try:
        await ctx_or_interaction.guild.unban(user)
    except:
        return await send_response(ctx_or_interaction, content=f"❌ Could not unban {user.mention}")
    embed = discord.Embed(title="Member Unbanned", 
                          description=f"{user.mention} has been unbanned", color=discord.Color.green())
    await send_response(ctx_or_interaction, embed=embed)
    announce_channel = ctx_or_interaction.guild.get_channel(MOD_CHANNEL)
    if announce_channel:
        await announce_channel.send(embed=embed)

# Prefix
@bot.command(name="unban")
@commands.has_permissions(ban_members=True)
async def unban_prefix(ctx, user_id: str):
    await unban_action(user_id, ctx)

# Slash
@bot.tree.command(name="unban", description="Unban a user by ID", guild=guild)
@app_commands.describe(user_id="User ID to unban")
async def unban_slash(interaction: discord.Interaction, user_id: str):
    if not interaction.user.guild_permissions.ban_members:
        return await interaction.response.send_message("❌ No permission", ephemeral=False)
    await interaction.response.defer(ephemeral=False)
    await unban_action(user_id, interaction)



# ---------- RUN BOT ----------
bot.run(TOKEN)