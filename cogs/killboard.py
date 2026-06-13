import discord
from discord.ext import commands, tasks
import aiohttp
import asyncio
from db.connection import killboard_collection
from datetime import datetime
from io import BytesIO
from PIL import Image, ImageDraw, ImageFont
from utils.price_fetcher import calculate_kill_value

from utils.price_fetcher import calculate_kill_value

class Killboard(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.check_killboard.start()

    def cog_unload(self):
        self.check_killboard.cancel()

    async def fetch_albion_events(self, guild_id, limit=10):
        """Obtiene eventos donde el gremio es el ASESINO (API oficial)."""
        url = f"https://gameinfo.albiononline.com/api/gameinfo/events?guildId={guild_id}&limit={limit}"
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url) as response:
                    if response.status == 200:
                        return await response.json()
                    else:
                        print(f"Error fetching Albion events: {response.status}")
                        return []
        except Exception as e:
            print(f"Exception fetching Albion events: {e}")
            return []

    async def fetch_global_events(self, limit=50):
        """Obtiene eventos globales para buscar MUERTES (API oficial)."""
        url = f"https://gameinfo.albiononline.com/api/gameinfo/events?limit={limit}"
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url) as response:
                    if response.status == 200:
                        return await response.json()
                    else:
                        return []
        except Exception as e:
            print(f"Exception fetching Global events: {e}")
            return []

    async def get_guild_id(self, guild_name):
        url = f"https://gameinfo.albiononline.com/api/gameinfo/search?q={guild_name}"
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url) as response:
                    if response.status == 200:
                        data = await response.json()
                        guilds = data.get('guilds', [])
                        for guild in guilds:
                            if guild['Name'].lower() == guild_name.lower():
                                return guild['Id']
            return None
        except Exception as e:
            print(f"Exception searching guild: {e}")
            return None

    async def generate_kill_image(self, event, estimated_value):
        """Genera la imagen principal con Stats, Gear y Damage Report."""
        killer = event.get("Killer", {})
        victim = event.get("Victim", {})
        
        killer_eq = killer.get("Equipment", {})
        victim_eq = victim.get("Equipment", {})
        
        # Configuración
        icon_size = 128
        padding = 10
        gear_padding = 0 # Espacio reducido entre items (Pegado)
        
        # Layout de Equipamiento (3 columnas x 4 filas)
        slot_coords = {
            'Head': (1, 0), 'Bag': (0, 0), 'MainHand': (0, 1), 'Armor': (1, 1),
            'OffHand': (2, 1), 'Shoes': (1, 2), 'Cape': (2, 0), 'Food': (2, 2),
            'Potion': (0, 2), 'Mount': (1, 3)
        }
        
        # Recalcular ancho del bloque con el nuevo padding
        gear_block_width = 3 * (icon_size + gear_padding)
        gear_block_height = 4 * (icon_size + gear_padding)
        
        center_width = 350 # Espacio central para stats (Reducido de 500)
        
        # Damage Report Data
        participants = event.get("Participants", [])
        participants = sorted(participants, key=lambda x: x.get("DamageDone", 0), reverse=True)
        top_participants = participants[:5] # Top 5 para la barra
        
        damage_section_height = 150 if top_participants else 0
        header_height = 110 # Header reducido (antes 180)
        gear_start_y = header_height + 20 # Bajamos los sets solo un poco (antes +60)
        
        width = (gear_block_width * 2) + center_width + (padding * 4)
        height = gear_start_y + gear_block_height + damage_section_height + (padding * 2)

        # Crear lienzo
        try:
            bg_image = Image.open("assets/imagen fondo.png").convert("RGBA")
            from PIL import ImageOps
            img = Image.new('RGBA', (width, height))
            bg_resized = ImageOps.fit(bg_image, (width, height), method=Image.Resampling.LANCZOS)
            img.paste(bg_resized, (0, 0))
        except:
            img = Image.new('RGBA', (width, height), (40, 40, 40, 255))
            
        draw = ImageDraw.Draw(img)
        
        # Fuentes NORMALIZADAS
        try:
            # Intentar cargar Arial (Windows/Local o si subiste los archivos)
            font_name = ImageFont.truetype("arialbd.ttf", 32) 
            font_info = ImageFont.truetype("arialbd.ttf", 24) 
            font_small = ImageFont.truetype("arial.ttf", 18) 
            font_damage = ImageFont.truetype("arial.ttf", 16) 
        except OSError:
            try:
                # Fallback para Linux (DejaVuSans es muy común en servidores)
                font_name = ImageFont.truetype("DejaVuSans-Bold.ttf", 32)
                font_info = ImageFont.truetype("DejaVuSans-Bold.ttf", 24)
                font_small = ImageFont.truetype("DejaVuSans.ttf", 18)
                font_damage = ImageFont.truetype("DejaVuSans.ttf", 16)
            except OSError:
                # Último recurso: Fuente por defecto (Diminuta)
                print("⚠️ ALERTA: No se encontraron fuentes (Arial ni DejaVu). Sube los archivos .ttf a la carpeta del bot.")
                font_name = ImageFont.load_default()
                font_info = ImageFont.load_default()
                font_small = ImageFont.load_default()
                font_damage = ImageFont.load_default()

        def draw_text_stroke(pos, text, font, fill="white"):
            draw.text(pos, text, fill=fill, font=font, stroke_width=2, stroke_fill="black")

        # --- POSICIONES ---
        center_x = width // 2
        killer_start_x = padding
        victim_start_x = width - gear_block_width - padding
        
        # --- HEADER (Nombres) ---
        # Killer (Left)
        k_name = killer.get("Name", "Unknown")
        k_guild = killer.get("GuildName", "")
        k_ip = int(killer.get("AverageItemPower", 0))
        draw_text_stroke((killer_start_x, padding + 10), k_name, font_name)
        draw_text_stroke((killer_start_x, padding + 50), k_guild, font_small)
        draw_text_stroke((killer_start_x, padding + 75), f"IP: {k_ip}", font_small)
        
        # Victim (Right)
        v_name = victim.get("Name", "Unknown")
        v_guild = victim.get("GuildName", "")
        v_ip = int(victim.get("AverageItemPower", 0))
        
        v_name_w = draw.textlength(v_name, font=font_name)
        v_guild_w = draw.textlength(v_guild, font=font_small)
        v_ip_w = draw.textlength(f"IP: {v_ip}", font=font_small)
        
        v_align_right = width - padding
        draw_text_stroke((v_align_right - v_name_w, padding + 10), v_name, font_name)
        draw_text_stroke((v_align_right - v_guild_w, padding + 50), v_guild, font_small)
        draw_text_stroke((v_align_right - v_ip_w, padding + 75), f"IP: {v_ip}", font_small)

        # --- CENTER STATS ---
        # Bajamos la info central
        stats_y = header_height + 20
        fame = event.get("TotalVictimKillFame", 0)
        date_str = event.get("TimeStamp", "").split("T")[0]
        time_str = event.get("TimeStamp", "").split("T")[1].split(".")[0] if "T" in event.get("TimeStamp", "") else ""
        
        current_y = stats_y
        
        # Helper para dibujar icono + texto centrado
        def draw_stat_icon(y, icon_file, text):
            try:
                icon = Image.open(icon_file).convert("RGBA")
                icon = icon.resize((48, 48)) # Iconos medianos (antes 64)
                img.paste(icon, (center_x - 24, y), icon)
                
                text_w = draw.textlength(text, font=font_info)
                draw_text_stroke((center_x - text_w/2, y + 55), text, font_info, fill=(255, 215, 0))
                return y + 90 # Salto ajustado
            except:
                # Fallback si no hay imagen
                text_w = draw.textlength(text, font=font_info)
                draw_text_stroke((center_x - text_w/2, y + 20), text, font_info, fill=(255, 215, 0))
                return y + 40

        # Fama
        current_y = draw_stat_icon(current_y, "assets/Fama.png", f"{fame:,}")
        
        # Valor (Agregado signo $)
        current_y = draw_stat_icon(current_y, "assets/silver.png", f"${estimated_value:,.0f}")
        
        # Fecha y Hora (Sin iconos, pegados)
        current_y += 15
        date_w = draw.textlength(date_str, font=font_info)
        draw_text_stroke((center_x - date_w/2, current_y), date_str, font_info)
        
        current_y += 30
        time_text = f"{time_str} UTC"
        time_w = draw.textlength(time_text, font=font_info)
        draw_text_stroke((center_x - time_w/2, current_y), time_text, font_info)

        # VS
        draw_text_stroke((center_x - 25, padding + 30), "VS", font_name, fill=(200, 50, 50))

        # --- GEAR DRAWING ---
        async with aiohttp.ClientSession() as session:
            async def draw_gear(items_dict, start_x, start_y):
                for key, (col, row) in slot_coords.items():
                    item = items_dict.get(key)
                    # Usar gear_padding reducido
                    x = start_x + col * (icon_size + gear_padding)
                    y = start_y + row * (icon_size + gear_padding)
                    
                    if item:
                        item_type = item.get("Type")
                        quality = item.get("Quality", 1)
                        count = item.get("Count", 1)
                        if item_type:
                            url = f"https://render.albiononline.com/v1/item/{item_type}?quality={quality}"
                            try:
                                async with session.get(url) as resp:
                                    if resp.status == 200:
                                        data = await resp.read()
                                        icon = Image.open(BytesIO(data)).convert("RGBA")
                                        icon = icon.resize((icon_size, icon_size))
                                        img.paste(icon, (x, y), icon)
                                        if count > 1:
                                            draw_text_stroke((x+5, y+80), str(count), font_name)
                            except: pass

            await draw_gear(killer_eq, killer_start_x, gear_start_y)
            await draw_gear(victim_eq, victim_start_x, gear_start_y)

        # --- DAMAGE REPORT BAR ---
        if top_participants:
            bar_y = gear_start_y + gear_block_height + 60 # Bajamos la barra un poco más para dar espacio
            bar_x = padding * 4
            bar_width = width - (padding * 8)
            bar_height = 30
            
            # Subimos el texto "Damage" para que no lo tape la barra
            draw_text_stroke((center_x - 40, bar_y - 35), "Damage", font_info)
            
            total_dmg = sum(p.get("DamageDone", 0) for p in top_participants)
            if total_dmg == 0: total_dmg = 1
            
            current_x = bar_x
            colors = [(180, 40, 40), (200, 100, 40), (200, 180, 40), (40, 180, 40), (40, 100, 180)]
            
            # Dibujar Barra
            for i, p in enumerate(top_participants):
                dmg = p.get("DamageDone", 0)
                pct = dmg / total_dmg
                seg_width = int(bar_width * pct)
                
                color = colors[i % len(colors)]
                draw.rectangle([current_x, bar_y, current_x + seg_width, bar_y + bar_height], fill=color)
                
                # Texto porcentaje dentro de la barra si cabe
                if seg_width > 40:
                    pct_text = f"{int(pct*100)}%"
                    tw = draw.textlength(pct_text, font=font_small)
                    draw_text_stroke((current_x + seg_width/2 - tw/2, bar_y + 5), pct_text, font_small)
                
                current_x += seg_width
            
            # Dibujar Leyenda (Abajo)
            legend_y = bar_y + bar_height + 10
            legend_x = bar_x
            
            for i, p in enumerate(top_participants):
                color = colors[i % len(colors)]
                p_name = p.get("Name", "Unknown")
                p_dmg = p.get("DamageDone", 0)
                
                # Cuadrito color
                draw.rectangle([legend_x, legend_y, legend_x + 15, legend_y + 15], fill=color, outline="black")
                
                # Texto
                text = f"{p_name} [{p_dmg}]"
                draw_text_stroke((legend_x + 20, legend_y), text, font_damage)
                
                legend_x += draw.textlength(text, font=font_damage) + 40 # Espacio para el siguiente

        buffer = BytesIO()
        img.save(buffer, format="PNG")
        buffer.seek(0)
        return discord.File(buffer, filename="kill_main.png")

    async def generate_inventory_image(self, event):
        """Genera imagen solo del inventario."""
        victim_inv = event.get("Victim", {}).get("Inventory", [])
        inv_items = [i for i in victim_inv if i is not None]
        
        if not inv_items:
            return None
            
        icon_size = 128
        padding = 10
        cols = 10
        import math
        rows = math.ceil(len(inv_items) / cols)
        
        width = (cols * (icon_size + padding)) + padding
        height = (rows * (icon_size + padding)) + padding + 40 # +40 header
        
        try:
            bg_image = Image.open("assets/imagen fondo.png").convert("RGBA")
            from PIL import ImageOps
            img = Image.new('RGBA', (width, height))
            bg_resized = ImageOps.fit(bg_image, (width, height), method=Image.Resampling.LANCZOS)
            img.paste(bg_resized, (0, 0))
        except:
            img = Image.new('RGBA', (width, height), (40, 40, 40, 255))
            
        draw = ImageDraw.Draw(img)
        
        try:
            font_bold = ImageFont.truetype("arialbd.ttf", 28)
            font_header = ImageFont.truetype("arialbd.ttf", 24)
        except:
            font_bold = ImageFont.load_default()
            font_header = ImageFont.load_default()
            
        draw.text((padding, 5), "INVENTORY", fill="white", font=font_header, stroke_width=2, stroke_fill="black")

        async with aiohttp.ClientSession() as session:
            for i, item in enumerate(inv_items):
                col = i % cols
                row = i // cols
                x = padding + col * (icon_size + padding)
                y = 40 + row * (icon_size + padding)
                
                item_type = item.get("Type")
                quality = item.get("Quality", 1)
                count = item.get("Count", 1)
                
                if item_type:
                    url = f"https://render.albiononline.com/v1/item/{item_type}?quality={quality}"
                    try:
                        async with session.get(url) as resp:
                            if resp.status == 200:
                                data = await resp.read()
                                icon = Image.open(BytesIO(data)).convert("RGBA")
                                icon = icon.resize((icon_size, icon_size))
                                img.paste(icon, (x, y), icon)
                                if count > 1:
                                    draw.text((x+5, y+80), str(count), fill="white", font=font_bold, stroke_width=2, stroke_fill="black")
                    except: pass
                    
        buffer = BytesIO()
        img.save(buffer, format="PNG")
        buffer.seek(0)
        return discord.File(buffer, filename="kill_inventory.png")

    @commands.command(name="setup_killboard")
    @commands.has_permissions(administrator=True)
    async def setup_killboard(self, ctx, guild_name: str, channel: discord.TextChannel = None):
        """Configura el killboard para un gremio de Albion y un canal de Discord."""
        channel = channel or ctx.channel
        msg = await ctx.send(f"🔍 Buscando ID para el gremio **{guild_name}**...")
        
        guild_id = await self.get_guild_id(guild_name)
        
        if not guild_id:
            await msg.edit(content=f"❌ No se encontró ningún gremio llamado **{guild_name}**.")
            return

        killboard_collection.update_one(
            {"_id": "config"},
            {"$set": {
                "albion_guild_id": guild_id,
                "albion_guild_name": guild_name,
                "discord_channel_id": channel.id,
                # Si no existe last_event_id, lo inicializamos en 0, si existe no lo tocamos
            }},
            upsert=True
        )
        
        # Asegurar que last_event_id exista si es nuevo
        config = killboard_collection.find_one({"_id": "config"})
        if "last_event_id" not in config:
             killboard_collection.update_one({"_id": "config"}, {"$set": {"last_event_id": 0}})
        
        await msg.edit(content=f"✅ Killboard configurado exitosamente.\n**Gremio:** {guild_name} ({guild_id})\n**Canal:** {channel.mention}")

    @commands.command(name="test_killboard")
    @commands.has_permissions(administrator=True)
    async def test_killboard(self, ctx, limit: int = 5):
        """Muestra los últimos N eventos. Si no hay muertes recientes, SIMULA una para probar el diseño."""
        config = killboard_collection.find_one({"_id": "config"})
        if not config:
            await ctx.send("❌ El killboard no está configurado.")
            return

        guild_id = config.get("albion_guild_id")
        if not guild_id:
            await ctx.send("❌ No hay ID de gremio configurado.")
            return

        await ctx.send(f"🔄 Buscando eventos recientes (Kills + Global Deaths)...")
        
        # 1. Fetch Kills
        kills = await self.fetch_albion_events(guild_id, limit=limit)
        
        # 2. Fetch Global Events (Deaths)
        global_events = await self.fetch_global_events(limit=50)
        deaths = [e for e in global_events if str(e.get("Victim", {}).get("GuildId")) == str(guild_id)]
        
        # 3. Combine
        all_events = kills + deaths
        
        # --- SIMULACIÓN DE MUERTE (Si no hay reales) ---
        simulated = False
        if not deaths and kills:
            # Tomamos una kill y la invertimos para simular una muerte
            mock_death = kills[0].copy()
            mock_death["EventId"] = 999999999 # Fake ID
            # Swap Killer/Victim
            original_killer = mock_death.get("Killer")
            original_victim = mock_death.get("Victim")
            mock_death["Killer"] = original_victim
            mock_death["Victim"] = original_killer
            # Asegurar que el "nuevo víctima" (nosotros) tenga el GuildId correcto para que el bot lo detecte como muerte
            mock_death["Victim"]["GuildId"] = guild_id
            
            all_events.append(mock_death)
            simulated = True

        # Deduplicate
        unique_events = {e['EventId']: e for e in all_events}.values()
        sorted_events = sorted(unique_events, key=lambda x: x["TimeStamp"], reverse=True)
        final_events = sorted_events[:limit]
        
        if not final_events:
            await ctx.send("❌ No se encontraron eventos recientes.")
            return

        # Reporte
        kills_count = 0
        deaths_count = 0
        for e in final_events:
            killer_id = e.get("Killer", {}).get("GuildId")
            if str(killer_id) == str(guild_id):
                kills_count += 1
            else:
                deaths_count += 1
        
        msg = f"📊 **Reporte:** {len(final_events)} eventos.\n⚔️ **Kills:** {kills_count}\n💀 **Deaths:** {deaths_count}"
        if simulated:
            msg += "\n⚠️ **Nota:** No se encontraron muertes recientes en el feed global, así que se **simuló una muerte** (invirtiendo una kill) para que puedas verificar el diseño."
            
        await ctx.send(msg + "\n\nEnviando imágenes...")

        for event in final_events:
            await self.post_event(ctx.channel, event, guild_id)
            await asyncio.sleep(1.5)
        
        await ctx.send("✅ Prueba finalizada.")

    @tasks.loop(seconds=30)
    async def check_killboard(self):
        try:
            config = killboard_collection.find_one({"_id": "config"})
            if not config:
                return

            guild_id = config.get("albion_guild_id")
            channel_id = config.get("discord_channel_id")
            last_event_id = config.get("last_event_id", 0)

            if not guild_id or not channel_id:
                return

            channel = self.bot.get_channel(channel_id)
            if not channel:
                # Si el canal no está en caché, intentar fetch
                try:
                    channel = await self.bot.fetch_channel(channel_id)
                except:
                    print(f"No se pudo encontrar el canal {channel_id}")
                    return

            events = await self.fetch_albion_events(guild_id, limit=50)
            global_events = await self.fetch_global_events(limit=50)
            
            # Filter deaths from global events
            deaths = [e for e in global_events if e.get("Victim", {}).get("GuildId") == guild_id]
            
            # Combine events (Kills + Deaths)
            all_events = events + deaths
            
            if not all_events:
                return

            # Filtrar eventos nuevos
            new_events = [e for e in all_events if e["EventId"] > last_event_id]
            
            # Deduplicate by EventId
            unique_events = {e["EventId"]: e for e in new_events}
            new_events = list(unique_events.values())
            
            if not new_events:
                return

            # Ordenar por ID ascendente (el más viejo primero) para postear en orden cronológico
            new_events.sort(key=lambda x: x["EventId"])

            for event in new_events:
                await self.post_event(channel, event, guild_id)
                
                # Actualizar ID inmediatamente
                killboard_collection.update_one(
                    {"_id": "config"},
                    {"$set": {"last_event_id": event["EventId"]}}
                )
                await asyncio.sleep(1.5) # Respetar rate limits de Discord y Albion

        except Exception as e:
            print(f"Error en check_killboard loop: {e}")

    async def post_event(self, channel, event, my_guild_id):
        killer = event.get("Killer", {})
        victim = event.get("Victim", {})
        
        # Determinar si es Kill o Death
        # Asegurar que comparamos strings
        is_kill = str(killer.get("GuildId")) == str(my_guild_id)
        
        if is_kill:
            color = discord.Color.green()
            title = f"⚔️ {killer.get('Name', 'Unknown')} asesinó a {victim.get('Name', 'Unknown')}"
        else:
            color = discord.Color.red()
            title = f"💀 {victim.get('Name', 'Unknown')} murió a manos de {killer.get('Name', 'Unknown')}"

        # Calcular valor estimado
        estimated_value = await calculate_kill_value(event)

        embed = discord.Embed(title=title, color=color, timestamp=datetime.utcnow())
        
        # Link al Killboard oficial
        event_id = event.get("EventId")
        embed.add_field(name="🔗 Detalles", value=f"[Ver en Albion Killboard](https://albiononline.com/killboard/kill/{event_id})", inline=False)
        embed.set_footer(text=f"Event ID: {event_id}")
        
        # Generar imagen principal (Stats + Gear + Damage)
        main_file = await self.generate_kill_image(event, estimated_value)
        embed.set_image(url="attachment://kill_main.png")
        
        try:
            await channel.send(embed=embed, file=main_file)
            
            # Generar y enviar inventario por separado si existe
            inv_file = await self.generate_inventory_image(event)
            if inv_file:
                inv_embed = discord.Embed(color=discord.Color.dark_grey())
                inv_embed.set_image(url="attachment://kill_inventory.png")
                await channel.send(embed=inv_embed, file=inv_file)

        except Exception as e:
            print(f"Error enviando embed al canal {channel.id}: {e}")

    @check_killboard.before_loop
    async def before_check_killboard(self):
        await self.bot.wait_until_ready()

async def setup(bot):
    await bot.add_cog(Killboard(bot))
