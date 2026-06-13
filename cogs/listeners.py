from discord.ext import commands

class Placeholder2(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

async def setup(bot):
    await bot.add_cog(Placeholder2(bot))
