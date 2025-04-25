# generación dinámica de cursos con múltiples imágenes + audios
import os
import subprocess
import base64
import hashlib
from gtts import gTTS
from PIL import Image
import openai

# === 1. Dividir guion en secciones ===
def dividir_guion_en_secciones(guion, palabras_por_seccion=350):
    palabras = guion.split()
    secciones = []
    for i in range(0, len(palabras), palabras_por_seccion):
        seccion = " ".join(palabras[i:i + palabras_por_seccion])
        secciones.append(seccion)
    return secciones

# === 2. Generar imagen con OpenAI por cada sección (imagen única por contenido) ===
def generar_imagen_por_seccion(texto, indice):
    prompt = f"Genera una imagen educativa y realista para el siguiente contenido: {texto[:300]}"
    prompt_hash = hashlib.md5(prompt.encode()).hexdigest()[:8]  
    ruta_origen = f"static/imagenes/imagen_{indice}_{prompt_hash}_original.png"
    ruta_final = f"static/imagenes/imagen_{indice}_{prompt_hash}.png"

    if not os.path.exists(ruta_final):
        response = openai.Image.create(
            model="dall-e-3",
            prompt=prompt,
            n=1,
            size="1024x1024",
            response_format="b64_json"
        )
        imagen_b64 = response['data'][0]['b64_json']
        imagen_bytes = base64.b64decode(imagen_b64)
        with open(ruta_origen, 'wb') as f:
            f.write(imagen_bytes)
            

        # Adaptar al tamaño 1280x720 con fondo blanco
        with Image.open(ruta_origen) as img:
            fondo = Image.new("RGB", (1280, 720), (255, 255, 255))
            img.thumbnail((1280, 720))
            x = (1280 - img.width) // 2
            y = (720 - img.height) // 2
            fondo.paste(img, (x, y))
            fondo.save(ruta_final)

    return ruta_final

# === 3. Generar audio con gTTS por cada sección ===
def generar_audio_por_seccion(texto, indice):
    ruta_audio = f"static/audios/seccion_{indice}.mp3"
    tts = gTTS(text=texto, lang='es')
    tts.save(ruta_audio)
    return ruta_audio

# === 4. Crear video dinámico por secciones individuales y unir ===
def crear_video_dinamico(rutas_imagenes, rutas_audios):
    videos_individuales = []

    for i in range(len(rutas_imagenes)):
        output_clip = f"static/videos/clip_{i}.mp4"
        subprocess.run([
            "ffmpeg", "-y",
            "-loop", "1", "-i", rutas_imagenes[i],
            "-i", rutas_audios[i],
            "-c:v", "libx264", "-tune", "stillimage",
            "-c:a", "aac", "-b:a", "192k",
            "-pix_fmt", "yuv420p",
            "-shortest", "-movflags", "+faststart",
            output_clip
        ])
        videos_individuales.append(output_clip)

    lista_txt = "static/videos/lista_videos.txt"
    with open(lista_txt, "w") as f:
        for v in videos_individuales:
            f.write(f"file '{v}'\n")

    video_final = "static/videos/curso_final.mp4"
    subprocess.run([
        "ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", lista_txt,
        "-c", "copy", "-movflags", "+faststart", video_final
    ])

    return video_final

# === 5. Obtener duración del audio ===
def get_audio_duration(audio_path):
    import wave
    import contextlib
    with contextlib.closing(wave.open(audio_path, 'rb')) as f:
        frames = f.getnframes()
        rate = f.getframerate()
        return frames / float(rate)

# === 6. Generador completo ===
def generar_video_completo(guion):
    secciones = dividir_guion_en_secciones(guion, palabras_por_seccion=350)
    rutas_imagenes = []
    rutas_audios = []
    for i, seccion in enumerate(secciones):
        img = generar_imagen_por_seccion(seccion, i)
        audio = generar_audio_por_seccion(seccion, i)
        rutas_imagenes.append(img)
        rutas_audios.append(audio)
    return crear_video_dinamico(rutas_imagenes, rutas_audios)

# uso:
# guion = "..."
# ruta_video = generar_video_completo(guion)
# luego guarda en mongo y muestra en dashboard