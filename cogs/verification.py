import discord
from discord.ext import commands, tasks
from discord import app_commands
import aiohttp
import asyncio
import math
from db.connection import registration_config_collection, registered_users_collection

class MemberPaginationView(discord.ui.View):
    def __init__(self, embeds):
        super().__init__(timeout=120)
        self.embeds = embeds
        self.current_page = 0
        self.update_buttons()

    def update_buttons(self):
        # Deshabilitar "Anterior" en la primera página y "Siguiente" en la última
        self.children[0].disabled = (self.current_page == 0)
        self.children[1].disabled = (self.current_page == len(self.embeds) - 1)

    @discord.ui.button(label="◀ Anterior", style=discord.ButtonStyle.primary)
    async def btn_prev(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.current_page -= 1
        self.update_buttons()
        await interaction.response.edit_message(embed=self.embeds[self.current_page], view=self)

    @discord.ui.button(label="Siguiente ▶", style=discord.ButtonStyle.primary)
    async def btn_next(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.current_page += 1
        self.update_buttons()
        await interaction.response.edit_message(embed=self.embeds[self.current_page], view=self)

class VerificationModal(discord.ui.Modal, title='Registro de Gremio'):
    player_name = discord.ui.TextInput(
        label='Nombre en Albion Online',
        placeholder='Ingresa tu nombre exacto del juego aquí...',
        required=True,
        max_length=50
    )

    def __init__(self, cog, config):
        super().__init__()
        self.cog = cog
        self.config = config

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.send_message(f"🔄 Verificando personaje **{self.player_name.value}**...", ephemeral=True)
        
        player_name = self.player_name.value.strip()
        player_data = await self.cog.search_player(player_name)
        
        if not player_data:
            await interaction.edit_original_response(content=f"❌ No pude encontrar a un jugador llamado **{player_name}** en Albion Online.")
            return

        target_guild_id = self.config.get("guild_id")
        
        if player_data.get('GuildId') != target_guild_id:
            await interaction.edit_original_response(content=f"❌ El personaje **{player_data.get('Name')}** NO pertenece al gremio **{self.config.get('guild_name')}**.")
            return

        role = interaction.guild.get_role(self.config.get("role_id"))
        if not role:
            await interaction.edit_original_response(content=f"❌ Error de configuración: el rol asignado ya no existe.")
            return

        try:
            await interaction.user.add_roles(role)
        except Exception as e:
            await interaction.edit_original_response(content=f"❌ No tengo permisos para asignarte el rol. Revisa mi jerarquía de roles.")
            return

        # Cambiar apodo (añadiendo [0CU])
        try:
            nuevo_apodo = f"[0CU] {player_data.get('Name')}"
            await interaction.user.edit(nick=nuevo_apodo)
        except discord.errors.Forbidden:
            print("No tengo permisos para cambiar el apodo de este usuario (probablemente sea superior en rango).")
        except Exception as e:
            print(f"Error cambiando apodo: {e}")

        # Guardar en la base de datos
        registered_users_collection.update_one(
            {"discord_id": str(interaction.user.id), "guild_id": str(interaction.guild.id)},
            {"$set": {
                "albion_id": player_data.get('Id'),
                "albion_name": player_data.get('Name')
            }},
            upsert=True
        )

        await interaction.edit_original_response(content=f"✅ Verificación exitosa. ¡Bienvenido a **{self.config.get('guild_name')}**!")

class VerificationView(discord.ui.View):
    def __init__(self, cog):
        # timeout=None para que el botón funcione incluso si el bot se reinicia
        super().__init__(timeout=None)
        self.cog = cog

    @discord.ui.button(label="Registrarse", style=discord.ButtonStyle.red, custom_id="verify_button_0cu", emoji="🛡️")
    async def verify_action(self, interaction: discord.Interaction, button: discord.ui.Button):
        config = registration_config_collection.find_one({"_id": str(interaction.guild.id)})
        if not config:
            await interaction.response.send_message("❌ El sistema de verificación no está configurado en este servidor.", ephemeral=True)
            return

        existing_user = registered_users_collection.find_one({"discord_id": str(interaction.user.id), "guild_id": str(interaction.guild.id)})
        if existing_user:
            await interaction.response.send_message(f"⚠️ Ya estás registrado como **{existing_user['albion_name']}**.", ephemeral=True)
            return

        # Abre el modal para que ingresen el nombre
        await interaction.response.send_modal(VerificationModal(self.cog, config))

class Verification(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.check_guild_members.start()

    def cog_unload(self):
        self.check_guild_members.cancel()

    async def search_player(self, player_name):
        url = f"https://gameinfo.albiononline.com/api/gameinfo/search?q={player_name}"
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url) as response:
                    if response.status == 200:
                        data = await response.json()
                        players = data.get('players', [])
                        # Buscar coincidencia exacta
                        for p in players:
                            if p.get('Name', '').lower() == player_name.lower():
                                return p
            return None
        except Exception as e:
            print(f"Error searching player: {e}")
            return None

    async def get_player_info(self, player_id):
        url = f"https://gameinfo.albiononline.com/api/gameinfo/players/{player_id}"
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url) as response:
                    if response.status == 200:
                        return await response.json()
            return None
        except Exception as e:
            print(f"Error getting player info: {e}")
            return None

    async def search_guild(self, guild_name):
        url = f"https://gameinfo.albiononline.com/api/gameinfo/search?q={guild_name}"
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url) as response:
                    if response.status == 200:
                        data = await response.json()
                        guilds = data.get('guilds', [])
                        for g in guilds:
                            if g.get('Name', '').lower() == guild_name.lower():
                                return g
            return None
        except Exception as e:
            print(f"Error searching guild: {e}")
            return None

    @app_commands.command(name="setup_verificacion", description="Configura el sistema de verificación automática para un canal y rol.")
    @app_commands.describe(
        canal="Canal donde se pondrá el botón verde de Registro",
        rol="El Rol que se le dará al usuario tras verificar",
        guild_name="Nombre exacto del gremio en Albion, ejemplo: Los Ocupas"
    )
    @app_commands.default_permissions(administrator=True)
    async def setup_verificacion(self, interaction: discord.Interaction, canal: discord.TextChannel, rol: discord.Role, guild_name: str):
        """Configura el sistema de verificación automática y crea el botón de registro."""
        await interaction.response.defer()
        
        guild_data = await self.search_guild(guild_name)
        if not guild_data:
            await interaction.followup.send(content=f"❌ No encontré un gremio llamado **{guild_name}** con coincidencia exacta.")
            return

        guild_id = guild_data['Id']
        real_guild_name = guild_data['Name']

        registration_config_collection.update_one(
            {"_id": str(interaction.guild.id)},
            {"$set": {
                "channel_id": canal.id,
                "role_id": rol.id,
                "guild_id": guild_id,
                "guild_name": real_guild_name
            }},
            upsert=True
        )

        embed = discord.Embed(
            title="🛡️ Verificación de Gremio",
            description=f"Para obtener el rol de miembro del gremio **{real_guild_name}** y acceso al servidor, necesitas registrar tu personaje.\n\n"
                        f"👉 Presiona el botón al final y escribe el nombre de tu personaje en Albion Online.",
            color=0xFFFFFF
        )
        
        # AQUÍ ESTÁ EL ESPACIO PARA LA IMAGEN 
        # Comentario: Imagen decorativa para el banner del panel de verificación del gremio.
        embed.set_image(url="https://images.unsplash.com/photo-1614850523459-c2f4c699c52e?q=80&w=600&auto=format&fit=crop") # Reemplaza por tu imagen de banner personalizada
        embed.set_footer(text="Asegúrate de escribir tu nombre exactamente como aparece en el juego.")
        
        await canal.send(embed=embed, view=VerificationView(self))
        await interaction.followup.send(content=f"✅ Sistema de verificación configurado correctamente.\nEl panel interactivo ha sido enviado a {canal.mention}.")

    @app_commands.command(name="verificados", description="Muestra una lista interactiva de los miembros verificados del servidor.")
    @app_commands.default_permissions(administrator=True)
    async def verificados(self, interaction: discord.Interaction):
        """Muestra una lista de todos los miembros verificados del servidor."""
        # Defer en caso de que tarde algo
        await interaction.response.defer()
        
        users = list(registered_users_collection.find({"guild_id": str(interaction.guild.id)}))
        
        if not users:
            await interaction.followup.send("❌ No hay miembros registrados actualmente.")
            return

        embeds = []
        items_per_page = 15
        total_pages = math.ceil(len(users) / items_per_page)

        for i in range(total_pages):
            embed = discord.Embed(
                title=f"👥 Miembros Verificados ({len(users)})",
                color=discord.Color.blue()
            )
            
            start_idx = i * items_per_page
            end_idx = start_idx + items_per_page
            page_users = users[start_idx:end_idx]

            description = ""
            for idx, user in enumerate(page_users, start=start_idx + 1):
                discord_id = user.get('discord_id')
                albion_name = user.get('albion_name')
                description += f"**{idx}.** <@{discord_id}> - `{albion_name}`\n"
            
            embed.description = description
            embed.set_footer(text=f"Página {i+1} de {total_pages}")
            embeds.append(embed)

        if len(embeds) == 1:
            await interaction.followup.send(embed=embeds[0])
        else:
            view = MemberPaginationView(embeds)
            await interaction.followup.send(embed=embeds[0], view=view)

    @app_commands.command(name="registrar_manual", description="Registra manualmente o migra a un usuario de Discord con un personaje en Albion.")
    @app_commands.describe(
        usuario="El usuario de Discord a registrar (Menciónalo)",
        albion_name="El nombre exacto de su personaje en Albion Online"
    )
    @app_commands.default_permissions(administrator=True)
    async def registrar_manual(self, interaction: discord.Interaction, usuario: discord.Member, albion_name: str):
        """Registra a un usuario manualmente asumiendo que ya es válido, pero validando contra la API."""
        await interaction.response.defer()

        # 1. Validar que el servidor tiene config
        config = registration_config_collection.find_one({"_id": str(interaction.guild.id)})
        if not config:
            await interaction.followup.send("❌ El sistema de verificación no está configurado en este servidor. Usa `/setup_verificacion` primero.")
            return

        target_guild_id = config.get("guild_id")
        target_guild_name = config.get("guild_name")
        role_id = config.get("role_id")
        
        # 2. Comprobar si ya está registrado en la base de datos
        existing_user = registered_users_collection.find_one({"discord_id": str(usuario.id), "guild_id": str(interaction.guild.id)})
        if existing_user:
            await interaction.followup.send(f"⚠️ {usuario.mention} ya está registrado como **{existing_user['albion_name']}**.")
            return

        # 3. Buscar en la API de Albion
        player_data = await self.search_player(albion_name)
        if not player_data:
            await interaction.followup.send(f"❌ No encontré un jugador llamado **{albion_name}** en Albion Online.")
            return

        # 4. Verificar Gremio
        if player_data.get("GuildId") != target_guild_id:
            await interaction.followup.send(
                f"❌ El jugador **{albion_name}** pertenece a **{player_data.get('GuildName', 'Ningún Gremio')}**, "
                f"no a **{target_guild_name}**."
            )
            return

        # 5. Intentar cambiar apodo
        try:
            await usuario.edit(nick=f"[0CU] {player_data['Name']}")
        except discord.Forbidden:
            print(f"No pude cambiar el apodo de {usuario.name} (faltan permisos).")

        # 6. Intentar asignar rol
        rol = interaction.guild.get_role(int(role_id))
        if rol:
            try:
                await usuario.add_roles(rol)
            except discord.Forbidden:
                print(f"No pude asignar el rol a {usuario.name}.")

        # 7. Guardar en base de datos
        registered_users_collection.insert_one({
            "discord_id": str(usuario.id),
            "guild_id": str(interaction.guild.id),
            "albion_name": player_data['Name'],
            "albion_id": player_data['Id']
        })

        await interaction.followup.send(f"✅ Se ha registrado y sincronizado exitosamente a {usuario.mention} como **{player_data['Name']}**.")

    @tasks.loop(hours=6)
    async def check_guild_members(self):
        """Tarea en segundo plano para verificar si siguen en el gremio."""
        try:
            # Traer todas las configuraciones de los diferentes servidores donde esté el bot
            configs = list(registration_config_collection.find({}))
            for config in configs:
                server_id = config.get("_id")
                target_guild_id = config.get("guild_id")
                role_id = config.get("role_id")
                
                guild = self.bot.get_guild(int(server_id))
                if not guild:
                    continue
                    
                role = guild.get_role(int(role_id))
                if not role:
                    continue

                # Traer usuarios registrados para este servidor
                users = list(registered_users_collection.find({"guild_id": server_id}))
                
                for user in users:
                    albion_id = user.get("albion_id")
                    discord_id = user.get("discord_id")
                    
                    member = guild.get_member(int(discord_id))
                    if not member:
                        # Si el miembro se fue de discord
                        continue
                        
                    # Consultar API de Albion por su ID
                    player_info = await self.get_player_info(albion_id)
                    if not player_info:
                        await asyncio.sleep(1)
                        continue # Evitar crashear si hay error de API
                        
                    if player_info.get("GuildId") != target_guild_id:
                        # Ya no está en el gremio
                        try:
                            await member.remove_roles(role)
                            registered_users_collection.delete_one({"_id": user["_id"]})
                            print(f"Quitado rol a {member.name} (ya no está en el gremio).")
                        except Exception as e:
                            print(f"Error quitando rol a {member.name}: {e}")
                            
                    await asyncio.sleep(1) # Respetar rate limit de Albion API
                    
        except Exception as e:
            print(f"Error en loop check_guild_members: {e}")

    @check_guild_members.before_loop
    async def before_check_guild_members(self):
        await self.bot.wait_until_ready()

async def setup(bot):
    await bot.add_cog(Verification(bot))
