import os
import discord
from discord.ext import commands
from config import DISCORD_TOKEN
import asyncio

# Intents necesarios (asegúrate de activarlos en el Developer Portal)
intents = discord.Intents.default()
intents.message_content = True
intents.members = True
intents.guilds = True
intents.voice_states = True

bot = commands.Bot(command_prefix="!", intents=intents)

@bot.event
async def on_ready():
    await bot.tree.sync() 
    print(f"✅ Bot conectado como {bot.user}")
    from cogs.splits import verificar_expiraciones_pendientes
    activity = discord.Activity(type=discord.ActivityType.watching,name=" sex ")  # También puedes usar otras opciones abajo
    await bot.change_presence(status=discord.Status.online, activity=activity)
    await verificar_expiraciones_pendientes(bot)


# Cargar cogs desde la carpeta /cogs
async def load_extensions():
    for filename in os.listdir("./cogs"):
        if filename.endswith(".py"):
            try:
                await bot.load_extension(f"cogs.{filename[:-3]}")
                print(f"🧩 Cog cargado: {filename}")
            except Exception as e:
                print(f"❌ Error cargando {filename}: {e}")

# Arranque del bot
async def main():
    async with bot:
        await load_extensions()
        
        # ADD VERIFICATION VIEW ON RESTART
        from db.connection import registration_config_collection
        from cogs.verification import VerificationView
        
        # Instanciar el View requiere el cog, lo obtenemos después de cargar las extensiones.
        cog = bot.get_cog("Verification")
        if cog:
            bot.add_view(VerificationView(cog))
            
        await bot.start(DISCORD_TOKEN)

asyncio.run(main())
