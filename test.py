from db.connection import client

# Verifica si puedes listar bases de datos
try:
    print("🔌 Conectando a MongoDB Atlas...")
    databases = client.list_database_names()
    print("✅ Conexión exitosa. Bases de datos disponibles:")
    for db in databases:
        print(f" - {db}")
except Exception as e:
    print("❌ Error al conectar con MongoDB:")
    print(e)
