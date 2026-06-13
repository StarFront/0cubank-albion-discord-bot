import os
from dotenv import load_dotenv

load_dotenv()

# Credenciales
DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
MONGO_URI = os.getenv("MONGO_URI")

# IDs de Discord
GUILD_ID = int(os.getenv("GUILD_ID", 0))
CANAL_SPLITS_ID = int(os.getenv("CANAL_SPLITS_ID", 0))
CATEGORIA_SPLITS_ID = int(os.getenv("CATEGORIA_SPLITS_ID", 0))
CANAL_LOGS_ID = int(os.getenv("CANAL_LOGS_ID", 0))
CANAL_DONACIONES_ID = int(os.getenv("CANAL_DONACIONES_ID", 0))
ROL_SPLIT_LOOTER_ID = int(os.getenv("ROL_SPLIT_LOOTER_ID", 0))
