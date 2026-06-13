from pymongo import MongoClient
from config import MONGO_URI

client = MongoClient(MONGO_URI)
db = client["ocubank"]  # Nombre de la base de datos

splits_collection = db["splits"]
casas_collection = db["casas"]
killboard_collection = db["killboard"]
registration_config_collection = db["registration_config"]
registered_users_collection = db["registered_users"]
