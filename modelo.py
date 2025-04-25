# modelo.py

from pymongo import MongoClient
from datetime import datetime
from config import MONGO_URI

client          = MongoClient(MONGO_URI)
db              = client["tfg_db"]

usuarios_col    = db["usuarios"]
respuestas_col  = db["respuestas"]
cursos_col      = db["cursos"]    # nueva colección
videos_col      = db["videos"]    # colección para cada sección/vídeo

# Índices
usuarios_col.create_index("email", unique=True)
respuestas_col.create_index("user_id")
cursos_col.create_index("user_id")
videos_col.create_index("curso_id")
