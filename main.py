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
    await member.send(f"Welcome to Royal Empire @{member.name}.. Need help? write !Help in https://discord.com/channels/1396670355422056609/1396801885322739743 ")

@bot.event
async def on_message(message):
    if message.author == bot.user:
        return
    
    if "shit" in message.content.lower():
        await message.delete()
        await message.channel.send(f"{message.author.mention} - don't use that word")

    if "!help" in message.content.lower():
        await message.channel.send(f" Hello {message.author.mention}! Welcome to the server \n You can take roles from https://discord.com/channels/1396670355422056609/1396726703564525688 \n and ping Staff in https://discord.com/channels/1396670355422056609/1396801885322739743 for further assistance")

    await bot.process_commands(message)


bot.run(token, log_handler=handler, log_level=logging.DEBUG)