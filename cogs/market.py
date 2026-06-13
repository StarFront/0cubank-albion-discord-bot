import discord
from discord.ext import commands
from discord import app_commands
from utils.price_fetcher import search_item, get_detailed_prices
from datetime import datetime
import re

class Market(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    # @commands.hybrid_command(name="precio", aliases=["price", "p"])
    # @app_commands.describe(item_name="Nombre del item a buscar (ej: Gran Hacha 4.3)")
    # async def precio(self, ctx, *, item_name: str):
    #     """Busca el precio de un item en las diferentes ciudades."""
        
    #     # 1. Parse Tier and Enchantment
    #     tier = None
    #     enchantment = None
    #     clean_name = item_name

    #     # Check for "4.3" format (Tier.Enchantment)
    #     match_dot = re.search(r'\b(\d+)\.(\d+)\b', clean_name)
    #     if match_dot:
    #         tier = match_dot.group(1)
    #         enchantment = match_dot.group(2)
    #         clean_name = clean_name.replace(match_dot.group(0), "").strip()
    #     else:
    #         # Check for "T4" or "Tier 4"
    #         match_tier = re.search(r'\b[tT]ier\s*(\d+)\b|\b[tT](\d+)\b', clean_name, re.IGNORECASE)
    #         if match_tier:
    #             tier = match_tier.group(1) or match_tier.group(2)
    #             clean_name = clean_name.replace(match_tier.group(0), "").strip()
            
    #         # Check for enchantment "@3" or ".3" (if not caught by 4.3)
    #         match_ench = re.search(r'[@\.](\d+)\b', clean_name)
    #         if match_ench:
    #             enchantment = match_ench.group(1)
    #             clean_name = clean_name.replace(match_ench.group(0), "").strip()

    #     # Defer response
    #     if ctx.interaction:
    #         await ctx.interaction.response.defer()
    #     else:
    #         await ctx.typing()

    #     # 2. Search Item
    #     items = await search_item(clean_name)
        
    #     if not items:
    #         msg = f"❌ No encontré ningún item llamado **{clean_name}**."
    #         if ctx.interaction:
    #             await ctx.interaction.followup.send(msg)
    #         else:
    #             await ctx.send(msg)
    #         return

    #     # 3. Filter Results
    #     target_item = None
        
    #     # If Tier is specified, look for matching UniqueName (e.g. T4_...)
    #     if tier:
    #         tier_prefix = f"T{tier}_"
    #         for item in items:
    #             if item.get('UniqueName', '').startswith(tier_prefix):
    #                 target_item = item
    #                 break
        
    #     # If no target yet (or no tier specified), try to find exact name match
    #     if not target_item:
    #         for item in items:
    #             if item.get('Name', '').lower() == clean_name.lower():
    #                 target_item = item
    #                 break
        
    #     # Fallback: Take the first item
    #     if not target_item:
    #         target_item = items[0]
            
    #     item_id = target_item.get('UniqueName')
    #     item_name_display = target_item.get('Name')
        
    #     if not item_id:
    #          item_id = target_item.get('id')
        
    #     if not item_id:
    #          msg = f"❌ Error al obtener ID del item."
    #          if ctx.interaction:
    #             await ctx.interaction.followup.send(msg)
    #          else:
    #             await ctx.send(msg)
    #          return

    #     # 4. Apply Enchantment to ID
    #     # Base ID usually looks like T4_MAIN_GREATAXE
    #     # Enchanted ID looks like T4_MAIN_GREATAXE@3
    #     if enchantment and int(enchantment) > 0:
    #         # Check if ID already has enchantment (unlikely from search, but possible)
    #         if "@" not in item_id:
    #             item_id = f"{item_id}@{enchantment}"
    #         else:
    #             # Replace existing enchantment if needed
    #             item_id = re.sub(r'@\d+', f"@{enchantment}", item_id)
            
    #         item_name_display += f" (Enchant {enchantment})"

    #     # 5. Obtener precios
    #     prices = await get_detailed_prices(item_id)
            
    #     if not prices:
    #         msg = f"❌ No se encontraron datos de mercado recientes para **{item_name_display}** ({item_id})."
    #         if ctx.interaction:
    #             await ctx.interaction.followup.send(msg)
    #         else:
    #             await ctx.send(msg)
    #         return

    #     # 6. Procesar precios
    #     city_prices = []
    #     for p in prices:
    #         city = p.get('city')
    #         price = p.get('sell_price_min', 0)
    #         quality = p.get('quality', 1)
    #         updated = p.get('sell_price_min_date')
            
    #         if price > 0:
    #             city_prices.append({
    #                 'city': city,
    #                 'price': price,
    #                 'quality': quality,
    #                 'updated': updated
    #             })
        
    #     if not city_prices:
    #         msg = f"⚠️ Hay datos del item, pero no hay órdenes de venta activas para **{item_name_display}**."
    #         if ctx.interaction:
    #             await ctx.interaction.followup.send(msg)
    #         else:
    #             await ctx.send(msg)
    #         return

    #     # Ordenar por precio ascendente
    #     city_prices.sort(key=lambda x: x['price'])
        
    #     # 7. Crear Embed
    #     embed = discord.Embed(
    #         title=f"💰 Precios: {item_name_display}",
    #         description=f"Listado de precios más bajos encontrados.",
    #         color=discord.Color.gold(),
    #         timestamp=datetime.utcnow()
    #     )
        
    #     # Thumbnail
    #     embed.set_thumbnail(url=f"https://render.albiononline.com/v1/item/{item_id}")
        
    #     best_price = city_prices[0]
    #     embed.add_field(
    #         name="🏆 Más Barato",
    #         value=f"**{best_price['city']}**: ${best_price['price']:,}",
    #         inline=False
    #     )
        
    #     # Agrupar por ciudad (mostrar el mínimo de cada ciudad)
    #     unique_cities = {}
    #     for entry in city_prices:
    #         c = entry['city']
    #         if c not in unique_cities:
    #             unique_cities[c] = entry
        
    #     # Ordenar ciudades por precio
    #     sorted_cities = sorted(unique_cities.values(), key=lambda x: x['price'])
        
    #     details = ""
    #     for entry in sorted_cities:
    #         # Calcular hace cuánto se actualizó
    #         try:
    #             last_update = datetime.strptime(entry['updated'], "%Y-%m-%dT%H:%M:%S")
    #             diff = datetime.utcnow() - last_update
    #             hours = diff.total_seconds() / 3600
    #             if hours < 1:
    #                 time_str = f"{int(diff.total_seconds()/60)}m"
    #             elif hours < 24:
    #                 time_str = f"{int(hours)}h"
    #             else:
    #                 time_str = f"{int(hours/24)}d"
    #         except:
    #             time_str = "?"

    #         details += f"**{entry['city']}**: ${entry['price']:,} (Hace {time_str})\n"
            
    #     embed.add_field(name="🏙️ Por Ciudad", value=details, inline=False)
    #     embed.set_footer(text=f"ID: {item_id} | Datos de Albion Online Data Project")
        
    #     if ctx.interaction:
    #         await ctx.interaction.followup.send(embed=embed)
    #     else:
    #         await ctx.send(embed=embed)

async def setup(bot):
    await bot.add_cog(Market(bot))
