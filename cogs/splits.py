import discord
from discord.ext import commands
from discord import app_commands
from db.connection import splits_collection
from config import (
    GUILD_ID, CANAL_SPLITS_ID, CATEGORIA_SPLITS_ID,
    CANAL_LOGS_ID, CANAL_DONACIONES_ID, ROL_SPLIT_LOOTER_ID
)
from datetime import datetime, timedelta
from bson.objectid import ObjectId
import asyncio
import re
from discord.ui import View, Select

# ==========================================
# CONFIGURACIÓN GENERAL
# ==========================================

# Configuración de Pagos
PORCENTAJE_SPLITER = 0.05  # 5%
PORCENTAJE_GREMIO = 0.00   # 0%

# Configuración de Tiempos
TIEMPO_ELIMINACION_CANAL = 86400  # 24 horas en segundos
TIEMPO_EXPIRACION_CASA_DIAS = 2   # Días que la casa permanece ocupada

# Listas de Opciones
PESTANAS_LOOT = [
    "LOOT MORROCO (Isla)", "LOOT PERUANO (Isla)", "LOOT VENECO (Isla)", 
    "1 SPLIT (HO)", "2 SPLIT (HO)", "3 SPLIT (HO)", "4 SPLIT (HO)"
]
CASAS_DISPONIBLES = [
    "Casa A (isla)", "Casa B (isla)", "Casa C (isla)", "Casa D (isla)",
    "Casa 1 (HO)", "Casa 2 (HO)", "Casa 3 (HO)", "Casa 4 (HO)", "Casa 5 (HO)", "Casa 6 (HO)"
]

# ==========================================
# FUNCIONES AUXILIARES
# ==========================================

def calcular_pagos(monto_total, num_participantes):
    """Calcula los montos a repartir."""
    total_spliter = monto_total * PORCENTAJE_SPLITER
    total_gremio = monto_total * PORCENTAJE_GREMIO
    restante = monto_total - total_spliter - total_gremio
    pago_individual = restante / num_participantes if num_participantes > 0 else 0
    return total_spliter, total_gremio, pago_individual

async def eliminar_canal_tarea(canal, tiempo):
    """Tarea en segundo plano para eliminar un canal después de un tiempo."""
    await asyncio.sleep(tiempo)
    try:
        await canal.delete()
    except Exception as e:
        print(f"Error eliminando canal {canal.name}: {e}")

async def liberar_casa_despues_de_expirar(split_id, casa_usada, fecha_expiracion, guild):
    """Libera la casa usada después de que expire el tiempo."""
    tiempo_restante = (fecha_expiracion - datetime.utcnow()).total_seconds()
    if tiempo_restante > 0:
        await asyncio.sleep(tiempo_restante)

    splits_collection.update_one(
        {"_id": ObjectId(split_id)},
        {"$set": {"casa_usada": None}}
    )

    canal_donaciones = guild.get_channel(CANAL_DONACIONES_ID)
    rol_split = guild.get_role(ROL_SPLIT_LOOTER_ID)
    
    if canal_donaciones:
        mencion = rol_split.mention if rol_split else "@here"
        await canal_donaciones.send(
            f"{mencion}\n"
            f"📢 Han pasado los 2 días del split asociado a la **{casa_usada}**.\n"
            f"Todo lo que quede allí debe ser llevado a **donaciones**.\n"
            f"🏠 La casa ha sido **liberada** y ya puede usarse en nuevos splits."
        )

async def verificar_expiraciones_pendientes(bot):
    """Verifica y reprograma la liberación de casas al reiniciar el bot."""
    now = datetime.utcnow()
    splits = splits_collection.find({
        "estado": "finalizado",
        "casa_usada": {"$ne": None}
    })

    canal_logs = bot.get_channel(CANAL_LOGS_ID)
    guild = bot.get_guild(GUILD_ID)

    if not guild:
        print(f"ERROR: No se encontró el servidor con ID {GUILD_ID}")
        return

    for split in splits:
        split_id = str(split["_id"])
        fecha_expiracion = split.get("fecha_expiracion")
        casa_usada = split.get("casa_usada")

        if not fecha_expiracion:
            continue

        tiempo_restante = (fecha_expiracion - now).total_seconds()

        if tiempo_restante <= 0:
            mensaje_log = f"[EXPIRADO] Liberando casa **{casa_usada}** del split `{split_id}` (ya vencido)."
            print(mensaje_log)
            if canal_logs:
                await canal_logs.send(mensaje_log)

            await liberar_casa_despues_de_expirar(split_id, casa_usada, fecha_expiracion, guild)
        else:
            mensaje_log = f"[REPROGRAMADO] Split `{split_id}` con casa **{casa_usada}** se liberará en `{int(tiempo_restante)}` segundos."
            print(mensaje_log)
            if canal_logs:
                await canal_logs.send(mensaje_log)

            asyncio.create_task(
                liberar_casa_despues_de_expirar(split_id, casa_usada, fecha_expiracion, guild)
            )

# ==========================================
# VISTAS Y MODALES
# ==========================================

class CrearSplitModal(discord.ui.Modal, title="Crear Split"):
    titulo = discord.ui.TextInput(label="Título del Split", placeholder="Ej: Roaming outpost dorados")
    monto_total = discord.ui.TextInput(label="Monto Total", placeholder="Ej: 20000000")
    creador = discord.ui.TextInput(label="Creador del contenido", placeholder="Ej: MarcosLeonV")
    hilo_url = discord.ui.TextInput(label="Link Mensaje/Hilo o ID", placeholder="Link o ID del canal/hilo destino", required=True)

    def __init__(self, autor, bot, pestana_loot, participantes):
        super().__init__()
        self.autor = autor
        self.bot = bot
        self.pestana_loot = pestana_loot
        self.participantes = participantes

    async def on_submit(self, interaction: discord.Interaction):
        try:
            monto = int(self.monto_total.value)
        except ValueError:
            await interaction.response.send_message("❌ El monto debe ser un número entero.", ephemeral=True)
            return

        participantes_data = [
            {"id": miembro.id, "nombre": miembro.display_name}
            for miembro in self.participantes
        ]

        # Calcular ganancias iniciales (referencial)
        total_spliter, total_gremio, _ = calcular_pagos(monto, len(participantes_data))

        split_data = {
            "titulo": self.titulo.value,
            "creador_contenido": self.creador.value,
            "monto_total": monto,
            "fecha_creacion": datetime.utcnow(),
            "fecha_expiracion": datetime.utcnow() + timedelta(days=TIEMPO_EXPIRACION_CASA_DIAS),
            "estado": "pendiente",
            "participantes": participantes_data,
            "pestana_loot": self.pestana_loot,
            "distribuidor": None,
            "casa_usada": None,
            "imagen_url": None,
            "hilo_url": self.hilo_url.value,
            "gremio": {"ganancia": total_gremio},
            "spliter": {"ganancia": total_spliter},
            "creado_por": {
                "id": self.autor.id,
                "nombre": self.autor.display_name
            },
            "canal_voz_usado": None
        }

        result = splits_collection.insert_one(split_data)
        split_id = str(result.inserted_id)

        # Publicar en canal de splits
        canal_splits = self.bot.get_channel(CANAL_SPLITS_ID)
        rol_split = interaction.guild.get_role(ROL_SPLIT_LOOTER_ID)
        
        if not canal_splits:
            await interaction.followup.send(f"❌ Error: No se encontró el canal de splits (ID: {CANAL_SPLITS_ID}). Revisa la configuración.", ephemeral=True)
            return

        if rol_split:
            mensaje_mencion = await canal_splits.send(rol_split.mention)
            # Eliminar mención después de 10s
            asyncio.create_task(eliminar_canal_tarea(mensaje_mencion, 10))

        view = TomarSplitView(bot=self.bot, split_id=split_id)
        participantes_nombres = ", ".join(p["nombre"] for p in participantes_data)
        
        file = discord.File("assets/split_sin_asignar.png", filename="split_sin_asignar.png")
        embed = discord.Embed(
            title=f"💸 Nuevo Split Disponible\n",
            description=f"**🔰 Título:** {self.titulo.value}\n\n"
                        f"**📂 Pestaña del Loot:** {self.pestana_loot}\n\n"
                        f"**👑 Creador del contenido:** {self.creador.value}\n\n"
                        f"**💰 Monto:** ${monto:,} en items\n\n"
                        f"**🐒 Participantes:** {participantes_nombres or 'Ninguno'}\n\n"
                        f"**📦 Distribuidor:** _Sin asignar_\n",
            color=discord.Color.orange()
        )
        # Comentario: Imagen decorativa local para un nuevo split de botín disponible.
        embed.set_image(url="attachment://split_sin_asignar.png")
        
        await canal_splits.send(
            embed=embed,
            file=file,
            view=view
        )

        await interaction.response.send_message(f"✅ Split creado correctamente con ID `{split_id}`", ephemeral=True)

class TomarSplitButton(discord.ui.Button):
    def __init__(self, bot, split_id):
        super().__init__(label="Tomar Split", style=discord.ButtonStyle.green)
        self.bot = bot
        self.split_id = split_id

    async def callback(self, interaction: discord.Interaction):
        try:
            rol_split = interaction.guild.get_role(ROL_SPLIT_LOOTER_ID)
            if rol_split not in interaction.user.roles:
                await interaction.response.send_message("❌ No tienes permiso para tomar splits.", ephemeral=True)
                return

            await interaction.response.defer(ephemeral=True)

            split = splits_collection.find_one({"_id": ObjectId(self.split_id)})
            if not split or split["estado"] != "pendiente":
                await interaction.followup.send("❌ Este split ya fue tomado o no existe.", ephemeral=True)
                return

            splits_collection.update_one(
                {"_id": ObjectId(self.split_id)},
                {
                    "$set": {
                        "estado": "asignado",
                        "distribuidor": {
                            "id": interaction.user.id,
                            "nombre": interaction.user.display_name
                        }
                    }
                }
            )

            guild = interaction.guild
            overwrites = {
                guild.default_role: discord.PermissionOverwrite(read_messages=False),
                interaction.user: discord.PermissionOverwrite(read_messages=True, send_messages=True),
                guild.me: discord.PermissionOverwrite(read_messages=True)
            }
            categoria = discord.utils.get(guild.categories, id=CATEGORIA_SPLITS_ID)
            
            nombre_canal = f"split-{self.split_id[-4:]}-{interaction.user.display_name}".lower().replace(" ", "-")
            canal_privado = await guild.create_text_channel(nombre_canal, overwrites=overwrites, category=categoria)

            await canal_privado.send(
                f"👋 Hola {interaction.user.mention}, este será tu canal para gestionar el split `{split['titulo']}`.\n"
                f"Elige la casa para realizar el split (Sí no hay es porque ahora mismo están todas ocupadas)."
            )

            # Advertencia si hay más de 14 participantes
            if len(split['participantes']) > 14:
                await canal_privado.send(
                    "⚠️ **ATENCIÓN:** Este split tiene más de 14 participantes.\n"
                    "Las casas estándar solo tienen capacidad para 14 personas.\n"
                    "Debes usar **Casa 1 (HO)** o **Casa A (Isla)** (30 cupos), o seleccionar un **par de casas**."
                )
            
            await canal_privado.send("🏠 Haz clic en el botón para comenzar el reparto:", view=ComenzarRepartoView(self.bot, self.split_id, canal_privado))

            nuevo_embed = discord.Embed(
                title="💸 Split Asignado\n",
                description=(
                    f"**🔰 Título:** {split['titulo']}\n\n"
                    f"**📂 Pestaña del Loot:** {split.get('pestana_loot', 'No especificada')}\n\n"
                    f"**👑 Creador del contenido:** {split['creador_contenido']}\n\n"
                    f"**💰 Monto:** ${split['monto_total']:,} en items\n\n"
                    f"**🐒 Participantes:** {', '.join(p['nombre'] for p in split['participantes'])}\n\n"
                    f"**📦 Distribuidor:** {interaction.user.mention}\n"
                ),
                color=discord.Color.green()
            )
            # Comentario: Imagen decorativa local para un split de botín que ya ha sido asignado a un distribuidor.
            file = discord.File("assets/split_asignado.png", filename="split_asignado.png")
            nuevo_embed.set_image(url="attachment://split_asignado.png")
            await interaction.message.edit(embed=nuevo_embed, attachments=[file], view=None)
            await interaction.followup.send(f"✅ Split asignado. Ve a {canal_privado.mention}", ephemeral=True)
        
        except Exception as e:
            print(f"Error en TomarSplitButton: {e}")
            try:
                await interaction.followup.send("❌ Ocurrió un error inesperado al tomar el split.", ephemeral=True)
            except:
                pass

class TomarSplitView(discord.ui.View):
    def __init__(self, bot, split_id):
        super().__init__(timeout=None)
        self.add_item(TomarSplitButton(bot, split_id))

class SplitCreationView(discord.ui.View):
    def __init__(self, bot, autor):
        super().__init__(timeout=120)
        self.bot = bot
        self.autor = autor
        self.pestana_loot = None
        self.participantes = []
        self.participantes_extra = []

    @discord.ui.select(placeholder="Selecciona la pestaña del loot", options=[
        discord.SelectOption(label=opcion, value=opcion) for opcion in PESTANAS_LOOT
    ])
    async def select_pestana(self, interaction: discord.Interaction, select: discord.ui.Select):
        self.pestana_loot = select.values[0]
        await interaction.response.defer()

    @discord.ui.select(cls=discord.ui.UserSelect, placeholder="Selecciona los participantes (1-25)", min_values=1, max_values=25)
    async def select_participantes(self, interaction: discord.Interaction, select: discord.ui.Select):
        self.participantes = select.values
        await interaction.response.defer()

    @discord.ui.select(cls=discord.ui.UserSelect, placeholder="Participantes Adicionales (Opcional)", min_values=1, max_values=25)
    async def select_participantes_extra(self, interaction: discord.Interaction, select: discord.ui.Select):
        self.participantes_extra = select.values
        await interaction.response.defer()

    @discord.ui.button(label="Continuar", style=discord.ButtonStyle.primary)
    async def continuar(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not self.pestana_loot:
            return await interaction.response.send_message("❌ Debes seleccionar una pestaña del loot.", ephemeral=True)
        
        # Unificar listas y eliminar duplicados por ID
        todos = self.participantes + self.participantes_extra
        participantes_unicos = list({p.id: p for p in todos}.values())

        if not participantes_unicos:
            return await interaction.response.send_message("❌ Debes seleccionar al menos un participante.", ephemeral=True)
        
        modal = CrearSplitModal(
            autor=self.autor,
            bot=self.bot,
            pestana_loot=self.pestana_loot,
            participantes=participantes_unicos
        )
        await interaction.response.send_modal(modal)

class CasaSelect(discord.ui.Select):
    def __init__(self, bot, split_id, canal):
        self.bot = bot
        self.split_id = split_id
        self.canal = canal

        # Obtener información del split
        split = splits_collection.find_one({"_id": ObjectId(split_id)})
        
        # Validación de seguridad: Si el split fue borrado manualmente
        if not split:
            super().__init__(placeholder="Error: Split no encontrado", options=[discord.SelectOption(label="Error", value="error")], disabled=True)
            return

        num_participantes = len(split["participantes"])
        pestana_loot = split.get("pestana_loot", "")

        now = datetime.utcnow()
        splits_ocupados = splits_collection.find({
            "fecha_expiracion": {"$gt": now},
            "casa_usada": {"$ne": None}
        })
        
        # Parsear casas ocupadas (incluyendo pares)
        casas_ocupadas_set = set()
        for s in splits_ocupados:
            casa = s["casa_usada"]
            if not casa: continue
            if " + " in casa:
                parts = casa.split(" + ")
                casas_ocupadas_set.update(parts)
            else:
                casas_ocupadas_set.add(casa)

        opciones = []

        # Determinar tipo de split (Isla vs HO)
        es_ho = "HO" in pestana_loot or "SPLIT" in pestana_loot
        es_isla = "Isla" in pestana_loot or "LOOT" in pestana_loot

        # Lógica para más de 14 participantes
        if num_participantes > 14:
            # Casas Grandes (30 cupos)
            if es_ho and "Casa 1 (HO)" not in casas_ocupadas_set:
                opciones.append(discord.SelectOption(label="Casa 1 (HO) [30 cupos]", value="Casa 1 (HO)"))
            
            if es_isla and "Casa A (isla)" not in casas_ocupadas_set:
                opciones.append(discord.SelectOption(label="Casa A (isla) [30 cupos]", value="Casa A (isla)"))

            # Pares de Casas Pequeñas
            if es_ho:
                pares_ho = [("Casa 2 (HO)", "Casa 3 (HO)"), ("Casa 4 (HO)", "Casa 5 (HO)")]
                for c1, c2 in pares_ho:
                    if c1 not in casas_ocupadas_set and c2 not in casas_ocupadas_set:
                        opciones.append(discord.SelectOption(label=f"{c1} + {c2}", value=f"{c1} + {c2}"))
            
            if es_isla:
                pares_isla = [("Casa B (isla)", "Casa C (isla)")]
                for c1, c2 in pares_isla:
                    if c1 not in casas_ocupadas_set and c2 not in casas_ocupadas_set:
                        opciones.append(discord.SelectOption(label=f"{c1} + {c2}", value=f"{c1} + {c2}"))

        else:
            # Menos de 14 participantes: Mostrar todas las disponibles individualmente (FILTRADAS)
            for casa in CASAS_DISPONIBLES:
                if casa in casas_ocupadas_set:
                    continue
                
                # Filtrar por tipo de split
                if es_isla and "(isla)" not in casa:
                    continue
                if es_ho and "(HO)" not in casa:
                    continue

                opciones.append(discord.SelectOption(label=casa, value=casa))

        if not opciones:
            opciones = [discord.SelectOption(label="No hay casas disponibles con capacidad suficiente", value="none", default=True)]

        super().__init__(placeholder="Selecciona una casa para repartir", options=opciones, min_values=1, max_values=1, disabled=len(opciones)==1 and opciones[0].value=="none")

    async def callback(self, interaction: discord.Interaction):
        if self.values[0] == "error":
             return await interaction.response.send_message("❌ El split ya no existe en la base de datos.", ephemeral=True)

        if self.values[0] == "none":
            return await interaction.response.send_message("❌ No hay casas disponibles en este momento.", ephemeral=True)

        casa_elegida = self.values[0]
        splits_collection.update_one(
            {"_id": ObjectId(self.split_id)},
            {"$set": {"casa_usada": casa_elegida}}
        )

        await interaction.response.send_message(f"🏠 Casa **{casa_elegida}** asignada exitosamente.", ephemeral=True)
        await self.canal.send(f"🏠 El split ahora se repartirá en **{casa_elegida}**.")

        split = splits_collection.find_one({"_id": ObjectId(self.split_id)})
        await enviar_resumen_embed(split, self.canal)

class RecargarCasasButton(discord.ui.Button):
    def __init__(self, bot, split_id, canal):
        super().__init__(label="🔄 Verificar Disponibilidad", style=discord.ButtonStyle.primary)
        self.bot = bot
        self.split_id = split_id
        self.canal = canal

    async def callback(self, interaction: discord.Interaction):
        view = CasaSelectView(self.bot, self.split_id, self.canal)
        await interaction.response.edit_message(view=view)

class CasaSelectView(View):
    def __init__(self, bot, split_id, canal):
        super().__init__(timeout=None)
        select = CasaSelect(bot, split_id, canal)
        self.add_item(select)
        
        # Si no hay casas disponibles (o error), agregar botón de recarga
        # Si es error, el select estará deshabilitado y con valor "error"
        if len(select.options) == 1 and (select.options[0].value == "none" or select.options[0].value == "error"):
            self.add_item(RecargarCasasButton(bot, split_id, canal))

class ComenzarRepartoView(View):
    def __init__(self, bot, split_id, canal):
        super().__init__(timeout=None)
        self.bot = bot
        self.split_id = split_id
        self.canal = canal

    @discord.ui.button(label="Comenzar Split", style=discord.ButtonStyle.primary)
    async def comenzar(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message("🏠 Selecciona la casa de distribución:", view=CasaSelectView(self.bot, self.split_id, self.canal))
        button.disabled = True
        await interaction.message.edit(view=self)

class ConfirmarFinalizarButton(discord.ui.Button):
    def __init__(self, canal, split_id, mensaje_original):
        super().__init__(label="Sí, finalizar", style=discord.ButtonStyle.danger)
        self.canal = canal
        self.split_id = split_id
        self.mensaje_original = mensaje_original

    async def callback(self, interaction: discord.Interaction):
        # Finaliza el split
        splits_collection.update_one(
            {"_id": ObjectId(self.split_id)},
            {"$set": {
                "estado": "finalizado",
                "fecha_expiracion": datetime.utcnow() + timedelta(days=TIEMPO_EXPIRACION_CASA_DIAS)
            }}
        )
        split = splits_collection.find_one({"_id": ObjectId(self.split_id)})
        participantes = split["participantes"]
        monto_total = split["monto_total"]
        
        total_spliter, total_gremio, pago_individual = calcular_pagos(monto_total, len(participantes))

        # Elimina mensaje de confirmación
        await interaction.message.delete()

        # Edita el mensaje original
        texto_participantes = ""
        for p in participantes:
            texto_participantes += f"💸 **{p['nombre']}** → `${pago_individual:,.0f}`\n"

        embed = discord.Embed(
            title=f"💰 Pagos del Split: {split['titulo']}",
            description=texto_participantes,
            color=discord.Color.gold()
        )
        embed.add_field(name="📦 Spliter", value=f"${total_spliter:,.0f}", inline=True)
        embed.add_field(name="🏰 Gremio", value=f"${total_gremio:,.0f}", inline=True)
        embed.add_field(name="🧾 Total", value=f"${monto_total:,.0f}", inline=True)

        if self.mensaje_original:
            await self.mensaje_original.edit(embed=embed, view=None)

        # Enviar resumen al canal de publicaciones finales o hilo especificado
        canal_destino = None
        input_destino = split.get("hilo_url", "").strip() if split.get("hilo_url") else ""
        
        if input_destino:
            # Caso 1: Es solo un ID numérico
            if input_destino.isdigit():
                try:
                    canal_destino = self.canal.guild.get_channel_or_thread(int(input_destino))
                    if not canal_destino:
                        canal_destino = await self.canal.guild.fetch_channel(int(input_destino))
                except Exception as e:
                    print(f"Error fetching channel by ID: {e}")

            # Caso 2: Es un enlace
            else:
                match = re.search(r"channels/(?:\d+|@me)/(\d+)(?:/(\d+))?", input_destino)
                if match:
                    channel_id = int(match.group(1))
                    message_id = match.group(2)

                    try:
                        channel = self.canal.guild.get_channel(channel_id)
                        if not channel:
                            channel = await self.canal.guild.fetch_channel(channel_id)
                        
                        if channel:
                            if message_id:
                                try:
                                    message = await channel.fetch_message(int(message_id))
                                    if message.thread:
                                        canal_destino = message.thread
                                    else:
                                        canal_destino = await message.create_thread(name=f"{split['casa_usada']}", auto_archive_duration=1440)
                                except Exception as e:
                                    print(f"Error con mensaje/hilo: {e}")
                                    canal_destino = channel
                            else:
                                canal_destino = channel
                    except Exception as e:
                        print(f"Error procesando link: {e}")

        if canal_destino:
            menciones = []
            for p in participantes:
                if p.get('id'):
                    menciones.append(f"<@{p['id']}> → `${pago_individual:,.0f}`")
                else:
                    menciones.append(f"**{p['nombre']}** → `${pago_individual:,.0f}`")

            distribuidor_mencion = (
                f"<@{split['distribuidor']['id']}>" if split["distribuidor"].get("id") else split["distribuidor"]["nombre"]
            )

            mensaje_texto = (
                f"📢 **Split Finalizado: {split['titulo']}**\n\n"
                f"📅 **Fecha:** <t:{int(split['fecha_creacion'].timestamp())}:D>\n"
                f"👑 **Creador del contenido:** {split['creador_contenido']}\n"
                f"📦 **Distribuidor:** {distribuidor_mencion}\n"
                f"🏠 **Casa:** {split['casa_usada']}\n\n"
                f"🕓 Tienen **2 días** para reclamar su loot.\n\n"
                f"💸 **Pagos:**\n" + "\n".join(menciones) + "\n\n"
                f"📷 Distribución de casas:"
            )

            try:
                # Comentario: Imagen instructiva local que muestra a los jugadores la ubicación física de las casas de cobro en la isla o HO.
                file_donde_cobro = discord.File("assets/donde_cobro.png", filename="donde_cobro.png")
                await canal_destino.send(mensaje_texto, file=file_donde_cobro)
            except Exception as e:
                await self.canal.send(f"❌ Error enviando el resumen al canal destino: {e}")
        else:
            await self.canal.send("⚠️ No se proporcionó un link/ID válido para el resumen, o no se pudo acceder al destino. El resumen no se publicó externamente, TE TOCA HACERLO MANUAL POR PENDEJO.")

        # Mensaje en el canal del split
        participantes_nombres = ", ".join([p['nombre'] for p in participantes])
        await self.canal.send(
            f"✅ El split **{split['titulo']}** fue finalizado correctamente.\n"
            f"Participantes: {participantes_nombres}\n"
            f"Distribuido en: **{split['casa_usada']}**"
        )
        await self.canal.send(f"⏳ Este canal se eliminará en {TIEMPO_ELIMINACION_CANAL // 3600} horas.")
        
        # Tarea en segundo plano para eliminar el canal
        asyncio.create_task(eliminar_canal_tarea(self.canal, TIEMPO_ELIMINACION_CANAL))

        # Iniciar cuenta regresiva para liberar casa
        asyncio.create_task(
            liberar_casa_despues_de_expirar(
                split_id=self.split_id,
                casa_usada=split["casa_usada"],
                fecha_expiracion=split["fecha_expiracion"],
                guild=self.canal.guild
            )
        )

class CancelarFinalizarButton(discord.ui.Button):
    def __init__(self):
        super().__init__(label="Cancelar", style=discord.ButtonStyle.secondary)

    async def callback(self, interaction: discord.Interaction):
        await interaction.message.delete()

class FinalizarSplitButton(discord.ui.Button):
    def __init__(self, canal, split_id, mensaje_original):
        super().__init__(label="✅ Finalizar Split", style=discord.ButtonStyle.green)
        self.canal = canal
        self.split_id = split_id
        self.mensaje_original = mensaje_original

    async def callback(self, interaction: discord.Interaction):
        await self.canal.send(
            content=f"⚠️ {interaction.user.mention}, ¿estás seguro de que deseas finalizar el split?",
            view=ConfirmacionFinalView(self.canal, self.split_id, self.mensaje_original)
        )
        await interaction.response.defer()

class ConfirmacionFinalView(discord.ui.View):
    def __init__(self, canal, split_id, mensaje_original):
        super().__init__(timeout=60)
        self.add_item(ConfirmarFinalizarButton(canal, split_id, mensaje_original))
        self.add_item(CancelarFinalizarButton())

class FinalizarSplitView(discord.ui.View):
    def __init__(self, canal, split_id, mensaje_original):
        super().__init__(timeout=None)
        self.add_item(FinalizarSplitButton(canal, split_id, mensaje_original))

async def enviar_resumen_embed(split, canal):
    participantes = split["participantes"]
    monto_total = split["monto_total"]
    
    total_spliter, total_gremio, pago_individual = calcular_pagos(monto_total, len(participantes))

    texto_participantes = ""
    for p in participantes:
        texto_participantes += f"💸 **{p['nombre']}** → `${pago_individual:,.0f}`\n"

    embed = discord.Embed(
        title=f"💰 Pagos del Split: {split['titulo']}",
        description=texto_participantes,
        color=discord.Color.gold()
    )
    embed.add_field(name="📦 Spliter", value=f"${total_spliter:,.0f}", inline=True)
    embed.add_field(name="🏰 Gremio", value=f"${total_gremio:,.0f}", inline=True)
    embed.add_field(name="🧾 Total", value=f"${monto_total:,.0f}", inline=True)

    if split.get("estado") != "finalizado":
        mensaje = await canal.send(embed=embed)
        await mensaje.edit(view=FinalizarSplitView(canal, str(split["_id"]), mensaje_original=mensaje))
    else:
        await canal.send(embed=embed)

class Splits(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="crear_split", description="Crea un nuevo split de botín")
    async def crear_split(self, interaction: discord.Interaction):
        # Verifica si el usuario tiene el rol necesario
        if not discord.utils.get(interaction.user.roles, id=ROL_SPLIT_LOOTER_ID) and not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message("❌ No tienes permiso para usar este comando. Necesitas el rol de Split Looter.", ephemeral=True)
            return
            
        await interaction.response.send_message("📝 Configura el split:", view=SplitCreationView(self.bot, interaction.user), ephemeral=True)

async def verificar_expiraciones_pendientes(bot):
    """Verifica y reprograma la liberación de casas al reiniciar el bot."""
    now = datetime.utcnow()
    splits = splits_collection.find({
        "estado": "finalizado",
        "casa_usada": {"$ne": None}
    })

    canal_logs = bot.get_channel(CANAL_LOGS_ID)
    guild = bot.get_guild(GUILD_ID)

    if not guild:
        print(f"ERROR: No se encontró el servidor con ID {GUILD_ID}")
        return

    for split in splits:
        split_id = str(split["_id"])
        fecha_expiracion = split.get("fecha_expiracion")
        casa_usada = split.get("casa_usada")

        if not fecha_expiracion:
            continue

        tiempo_restante = (fecha_expiracion - now).total_seconds()

        if tiempo_restante <= 0:
            mensaje_log = f"[EXPIRADO] Liberando casa **{casa_usada}** del split `{split_id}` (ya vencido)."
            print(mensaje_log)
            if canal_logs:
                await canal_logs.send(mensaje_log)

            await liberar_casa_despues_de_expirar(split_id, casa_usada, fecha_expiracion, guild)
        else:
            mensaje_log = f"[REPROGRAMADO] Split `{split_id}` con casa **{casa_usada}** se liberará en `{int(tiempo_restante)}` segundos."
            print(mensaje_log)
            if canal_logs:
                await canal_logs.send(mensaje_log)

            asyncio.create_task(
                liberar_casa_despues_de_expirar(split_id, casa_usada, fecha_expiracion, guild)
            )

async def setup(bot):
    await bot.add_cog(Splits(bot))
