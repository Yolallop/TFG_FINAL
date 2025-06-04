from pymongo import MongoClient
from bson import ObjectId
from datetime import datetime
from config import MONGODB_URI

client = MongoClient(MONGODB_URI)
db = client.tfg_db

# Colecciones
usuarios_col   = db.usuarios
respuestas_col = db.respuestas
cursos_col     = db.cursos
videos_col     = db.videos
eventos_col    = db.eventos

# Índices (pueden quedarse tal cual)
def crear_usuario(nombre: str, email: str, password: str) -> ObjectId | None:
    if usuarios_col.find_one({"email": email}):
        return None  # Ya existe

    hashed_password = bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt())

    usuario = {
        "nombre": nombre,
        "email": email,
        "password": hashed_password,
        "verificado": False,
        "fecha_registro": datetime.utcnow()
    }

    result = usuarios_col.insert_one(usuario)
    return result.inserted_id
# ——— Curso CRUD ———

def create_course(user_id: str,
                  tema: str,
                  objetivos: str,
                  experiencia: str,
                  origin: str = 'personalizado') -> ObjectId:
    """
    Crea un curso.
    origin puede ser 'initial', 'personalizado', etc.
    """
    curso = {
        "user_id":     user_id,
        "tema":        tema,
        "objetivos":   objetivos,
        "experiencia": experiencia,
        "origin":      origin,
        "created_at":  datetime.utcnow(),
        "completed":   False,
        "lecciones":   []
    }
    result = cursos_col.insert_one(curso)
    return result.inserted_id


def add_lessons_to_course(course_id: ObjectId,
                          lesson_ids: list[ObjectId]) -> None:
    cursos_col.update_one(
        {"_id": course_id},
        {"$push": {"lecciones": {"$each": lesson_ids}}}
    )


def mark_course_completed(course_id: ObjectId) -> None:
    cursos_col.update_one(
        {"_id": course_id},
        {"$set": {"completed": True, "completed_at": datetime.utcnow()}}
    )


def get_user_courses(user_id: str) -> list[dict]:
    return list(
        cursos_col
        .find({"user_id": user_id})
        .sort("created_at", -1)
    )


# ——— Vídeo CRUD ———

def create_video(course_id: ObjectId,
                 user_id: str,
                 titulo: str,
                 descripcion: str,
                 script: str,
                 video_path: str,
                 imagen: str,
                 fuentes: list) -> ObjectId:
    video = {
        "course_id":  course_id,
        "user_id":    user_id,
        "titulo":     titulo,
        "descripcion":descripcion,
        "script":     script,
        "video_path": video_path,
        "imagen":     imagen,
        "fuentes":    fuentes
    }
    result = videos_col.insert_one(video)
    return result.inserted_id


def get_course_videos(course_id: ObjectId) -> list[dict]:
    return list(videos_col.find({"course_id": course_id}))
