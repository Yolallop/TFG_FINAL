# curso.py
import os
import re
import subprocess
import logging
import base64

import openai
from gtts import gTTS
from PIL import Image

from config import OPENAI_API_KEY

# ——— Configuración de logging —————————————————————————
logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

# ——— Cliente OpenAI —————————————————————————————————————
openai.api_key = OPENAI_API_KEY

def chat_with_fallback(messages, temperature=0.7):
    """
    Intenta GPT-4 y, si falla por cuota, cae en GPT-3.5-turbo.
    """
    try:
        return openai.ChatCompletion.create(
            model="gpt-4",
            messages=messages,
            temperature=temperature
        ).choices[0].message.content
    except openai.error.RateLimitError:
        logging.warning("❗ GPT-4 fuera de cuota, usando gpt-3.5-turbo")
        return openai.ChatCompletion.create(
            model="gpt-3.5-turbo",
            messages=messages,
            temperature=temperature
        ).choices[0].message.content

class Tema:
    def __init__(self, titulo: str, contenido: str, script: list[dict]):
        self.titulo    = titulo
        self.contenido = contenido
        self.script    = script  # [{"id":…, "narration":…, "visual_description":…}, …]
        self.video_id  = ""      # Ruta relativa al vídeo final

class Curso:
    def __init__(self, titulo: str):
        self.titulo = titulo
        self.topics: list[Tema] = []

    def add_topic(self, tema: Tema):
        self.topics.append(tema)

    def generate_course_content(self) -> "Curso":
        for topic in self.topics:
            topic.video_id = self._generate_video_for_topic(topic)
        return self

    def _generate_video_for_topic(self, topic: Tema) -> str:
        # Nombre seguro
        safe_base = re.sub(r"[^\w]", "_", topic.titulo, flags=re.ASCII)

        # Crear carpetas
        os.makedirs("static/audios", exist_ok=True)
        os.makedirs("static/imagenes", exist_ok=True)
        os.makedirs("static/videos", exist_ok=True)

        escena_files = []
        for scene in topic.script:
            sid = scene["id"]

            # 1) Audio con gTTS
            audio_rel = f"audios/{safe_base}_{sid}.mp3"
            audio_out = os.path.join("static", audio_rel)
            tts = gTTS(scene["narration"], lang="es")
            tts.save(audio_out)
            scene["audio_path"] = audio_rel
            logging.info(f"🔊 Audio guardado en {audio_out}")

            # 2) Imagen con DALL·E 3 (1024×1024)
            img_rel = f"imagenes/{safe_base}_{sid}.png"
            img_out = os.path.join("static", img_rel)
            try:
                resp = openai.Image.create(
                    model="dall-e-3",
                    prompt=scene["visual_description"],
                    n=1,
                    size="1024x1024",
                    response_format="b64_json"
                )
                b64 = resp.data[0].b64_json
                img_bytes = base64.b64decode(b64)
                with open(img_out, "wb") as f:
                    f.write(img_bytes)
                logging.info(f"🖼 Imagen guardada en {img_out}")
            except Exception as e:
                logging.error(f"❌ DALL·E falló: {e}")
                # Fallback: imagen negra
                Image.new("RGB", (1024, 1024), (0, 0, 0)).save(img_out)
                logging.warning(f"⚠️ Imagen fallback en {img_out}")
            scene["image_path"] = img_rel

            # 3) Vídeo de la escena con ffmpeg
            vid_rel = f"videos/{safe_base}_{sid}.mp4"
            vid_out = os.path.join("static", vid_rel)
            subprocess.run([
                "ffmpeg", "-y",
                "-loop", "1", "-i", img_out,
                "-i", audio_out,
                "-c:v", "libx264", "-tune", "stillimage",
                "-c:a", "aac", "-b:a", "192k",
                "-pix_fmt", "yuv420p",
                "-shortest",
                vid_out
            ], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            logging.info(f"✅ Escena vídeo creado en {vid_out}")

            escena_files.append(os.path.abspath(vid_out))

        # Si solo hay una escena, devolvemos esa ruta
        if len(escena_files) == 1:
            return escena_files[0].split("static/")[-1]

        # 4) Concatenar varias escenas
        list_txt = os.path.abspath(f"static/videos/{safe_base}_list.txt")
        with open(list_txt, "w", encoding="utf-8") as f:
            for fn in escena_files:
                f.write(f"file '{fn}'\n")

        final_rel = f"videos/{safe_base}_full.mp4"
        final_out = os.path.join("static", final_rel)
        subprocess.run([
            "ffmpeg", "-y",
            "-f", "concat", "-safe", "0",
            "-i", list_txt,
            "-c", "copy",
            final_out
        ], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        logging.info(f"🎞 Vídeo final en static/{final_rel}")

        return final_rel

# ——— Funciones auxiliares de guión —————————————————————————————————

def generar_guion(respuestas) -> str:
    """
    Genera el texto completo del curso usando GPT (con fallback).
    """
    prompt = (
        f"Eres un profesor experto. Crea un curso introductorio dividido en 3 secciones, "
        f"tema '{respuestas['intereses']}', nivel {respuestas['experiencia']}, "
        f"objetivo '{respuestas['objetivos']}'.\n\n"
        "Formato:\n"
        "Curso 1: Título\nContenido... (350-500 palabras)\n\n"
        "Curso 2: Título\nContenido... (350-500 palabras)\n\n"
        "Curso 3: Título\nContenido... (350-500 palabras)\n"
    )
    return chat_with_fallback([{"role": "user", "content": prompt}])

def dividir_secciones(texto: str) -> list[tuple[str, str]]:
    """
    Separa el texto devuelto por GPT en [(titulo, cuerpo), ...].
    """
    partes = re.split(r"(?=Curso \d+:)", texto)
    out = []
    for p in partes:
        p = p.strip()
        if not p:
            continue
        titulo, _, cuerpo = p.partition("\n")
        out.append((titulo.strip(), cuerpo.strip()))
    return out
