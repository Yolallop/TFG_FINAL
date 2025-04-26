from flask import Flask, render_template, request, redirect, url_for, flash, session
import logging
import os
import openai
import bcrypt
import requests
from pathlib import Path
from gtts import gTTS
import time
import subprocess
from pydub.utils import mediainfo

# Importar la clave de la API de OpenAI desde el archivo modelo.py
from config import OPENAI_API_KEY

# Configuración de la aplicación Flask
app = Flask(__name__, static_folder='static', template_folder='templates')
app.secret_key = 'clave_super_secreta'
app.config['TEMPLATES_AUTO_RELOAD'] = True
app.jinja_env.auto_reload = True
app.debug = True

# Configuración de la API de OpenAI usando la clave importada
openai.api_key = OPENAI_API_KEY

# Configuración de MongoDB
from pymongo import MongoClient
mongo = MongoClient("mongodb://localhost:27017")
db = mongo.tfg_db
users = db.usuarios
prefs = db.respuestas
vids = db.videos

# Crear carpetas necesarias
os.makedirs("static/audios", exist_ok=True)
os.makedirs("static/imagenes", exist_ok=True)
os.makedirs("static/videos", exist_ok=True)

log = logging.getLogger('werkzeug')
log.setLevel(logging.DEBUG)

@app.route('/')
def home():
    return render_template('index.html')

# Registro de usuario
@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        nombre = request.form['nombre'].strip()
        email = request.form['email'].lower().strip()
        password = request.form['password'].encode('utf-8')

        if users.find_one({"email": email}):
            flash('El correo ya está registrado.', 'danger')
            return redirect(url_for('register'))

        hashed = bcrypt.hashpw(password, bcrypt.gensalt())
        users.insert_one({"nombre": nombre, "email": email, "password": hashed})
        u = users.find_one({"email": email})
        session['user_id'] = str(u['_id'])
        session['usuario'] = nombre

        return redirect(url_for('preguntas'))
    return render_template('register.html')
@app.route('/evaluacion')
def evaluacion():
    return render_template('evaluacion.html')

# Login de usuario
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form['email'].lower().strip()
        password = request.form['password'].encode('utf-8')
        u = users.find_one({"email": email})

        if u and bcrypt.checkpw(password, u['password']):
            session['user_id'] = str(u['_id'])
            session['usuario'] = u['nombre']
            return redirect(url_for('dashboard'))

        flash('Credenciales incorrectas', 'danger')

    return render_template('login.html')

# Logout de usuario
@app.route('/logout')
def logout():
    session.clear()
    flash("Sesión cerrada", "info")
    return redirect(url_for('home'))

# Preguntas de usuario (preferencias)
@app.route('/preguntas', methods=['GET', 'POST'])
def preguntas():
    if 'user_id' not in session:
        return redirect(url_for('login'))

    if request.method == 'POST':
        intereses = ",".join(request.form.getlist('intereses'))
        objetivos = request.form['objetivos']
        experiencia = request.form['experiencia']

        nueva_respuesta = {
            "user_id": session['user_id'],
            "intereses": intereses,
            "objetivos": objetivos,
            "experiencia": experiencia
        }

        prefs.replace_one({"user_id": session['user_id']}, nueva_respuesta, upsert=True)
        return redirect(url_for('dashboard'))

    return render_template('preguntas.html')

@app.route('/dashboard')
def dashboard():
    if 'user_id' not in session:
        return redirect(url_for('login'))

    usuario = session['usuario']
    respuestas = prefs.find_one({"user_id": session['user_id']})
    videos = vids.find({"user_id": session['user_id']})

    # Verificar si los archivos de video existen
    for video in videos:
        video_path = os.path.join('static', 'videos', video['video_path'])

        if os.path.exists(video_path):
            print(f"El archivo {video_path} existe, puedes proceder a mostrarlo")
        else:
            print(f"El archivo {video_path} no existe, maneja el error")
            flash(f"El video {video['video_path']} no se encuentra disponible.", 'danger')

    # Renderizar el dashboard con la información
    return render_template('dashboard.html', usuario=usuario, respuestas=respuestas, videos=videos)

@app.route('/generar_curso', methods=['POST'])
def generar_curso():
    if 'user_id' not in session:
        return redirect(url_for('login'))

    # 1) Recupero las respuestas del usuario
    respuestas = prefs.find_one({"user_id": session['user_id']})
    if not respuestas:
        flash("Debes completar el formulario de preferencias primero.", "warning")
        return redirect(url_for('preguntas'))

    # 2) Genero el guion usando esas respuestas
    guion = generar_guion_dinamico(respuestas)

    # 3) Genero el vídeo y obtengo la ruta completa
    ruta_video, video_imagenes = generar_video_completo(guion, max_videos=3)

    # DEBUG opcional: imprime en consola la ruta completa que devolvió la función
    print(f"[DEBUG] Video generado en ruta: {ruta_video}")
    print("[DEBUG] contenidos de static/videos:", os.listdir("static/videos"))

    # 4) Extraigo solo el nombre de fichero real del vídeo
    basename = os.path.basename(ruta_video)  # ej. "final_video_1745686929.mp4"
     print("[DEBUG] guardando en BD video_path =", f"videos/{basename}")

    # 5) Selecciono la miniatura (si vino como lista, cojo la primera)
    if isinstance(video_imagenes, list) and video_imagenes:
        imagen_path = video_imagenes[0]
    else:
        imagen_path = video_imagenes

    # 6) Quito el prefijo "static/" para almacenar en la BD
    imagen_db = imagen_path.replace("static/", "")

    # 7) Construyo y guardo el documento en Mongo, usando los nombres reales
    video = {
        "user_id": session['user_id'],
        "titulo": "Curso Personalizado",
        "descripcion": guion[:200],
        "script": guion,
        "video_path": f"videos/{basename}",  # coincide con static/videos/{basename}
        "imagen": imagen_db                   # coincide con static/imagenes/{imagen_db}
    }
    vids.insert_one(video)

    flash("Curso generado exitosamente 🎉", "success")
    return redirect(url_for('dashboard'))


# Función para generar guion
# Función para generar guion
def generar_guion_dinamico(respuestas):
    prompt = f"""
    Eres un experto creando cursos online. Crea un guion para un curso sobre el tema: {respuestas['intereses']}.
    El estudiante tiene nivel {respuestas['experiencia']} y su objetivo es: {respuestas['objetivos']}.
    El guion debe tener entre 350 y 500 palabras por sección y debe ser adecuado para un video de 3 a 4 minutos de duración.
    """
    response = openai.ChatCompletion.create(
        model="gpt-3.5-turbo",
        messages=[
            {"role": "system", "content": "Eres un profesor experto en crear cursos online."},
            {"role": "user", "content": prompt}
        ],
        max_tokens=500
    )
    return response['choices'][0]['message']['content'].strip()

# Función para generar imágenes con OpenAI
def generate_image(prompt, id):
    result = openai.Image.create(prompt=prompt, n=1, size="1024x1024")
    image_url = result['data'][0]['url']
    image_path = os.path.join("static/imagenes", f"{id}.png")
    response = requests.get(image_url, timeout=30)
    if response.status_code == 200:
        with open(image_path, "wb") as f:
            f.write(response.content)
    return image_path

# Función para generar audio con gTTS
def generate_audio(texto, id):
    """
    Genera un MP3 desde un texto con gTTS, lo guarda en static/audios/{id}.mp3
    y comprueba en consola que no esté vacío.
    """
    audio_file = os.path.join("static", "audios", f"{id}.mp3")
    tts = gTTS(text=texto, lang='es')
    tts.save(audio_file)

    # DEBUG: comprueba que realmente se escribió algo
    size = os.path.getsize(audio_file)
    print(f"[DEBUG] Audio guardado en {audio_file}, {size} bytes")

    return audio_file

# Función para generar video con FFmpeg
def generar_video_con_ffmpeg(imagen, audio, output_video):
    audio_duration = get_audio_duration(audio)
    command = [
        'ffmpeg', '-y', '-loop', '1', '-framerate', '2', '-t', str(audio_duration),
        '-i', imagen, '-i', audio, '-c:v', 'libx264', '-preset', 'veryfast',
        '-c:a', 'aac', '-b:a', '192k', '-pix_fmt', 'yuv420p', '-shortest', output_video
    ]
    subprocess.run(command, check=True)

# Función para obtener duración de audio
def get_audio_duration(audio_path):
    info = mediainfo(audio_path)
    return float(info['duration'])

# Función para combinar videos generados
def combine_videos(video_parts, output_video):
    inputs = " ".join([f"-i \"{os.path.abspath(video)}\"" for video in video_parts])
    command = f"ffmpeg {inputs} -c copy {os.path.abspath(output_video)}"
    subprocess.run(command, shell=True, check=True)

# Función para generar video completo
import time  # Importa time para usar el timestamp

# Función para generar el video completo
def generar_video_completo(guion, max_videos):
    scenes = guion.split("\n\n")
    video_parts = []
    video_imagenes = []  # Lista de imágenes generadas
    
    for idx, scene in enumerate(scenes[:max_videos]):
        prompt = f"Genera una imagen para: {scene}"
        image_path = generate_image(prompt, idx)
        audio_path = generate_audio(scene, idx)
        
        # Usar timestamp para asegurar nombre único
        timestamp = int(time.time())  # Obtener el tiempo actual en segundos
        video_filename = f"video_{timestamp}_{idx}.mp4"  # Crear un nombre único basado en timestamp
        
        video_path = os.path.join("static/videos", video_filename)
        video_parts.append(video_path)
        generar_video_con_ffmpeg(image_path, audio_path, video_path)
        
        video_imagenes.append(image_path)

    # Generar un nombre único para el video final usando timestamp
    final_timestamp = int(time.time())  # Usamos el timestamp nuevamente para el video final
    final_video_filename = f"final_video_{final_timestamp}.mp4"  # Nombre único basado en el timestamp
    final_video_path = os.path.join("static/videos", final_video_filename)
    
    combine_videos(video_parts, final_video_path)

    return final_video_path, video_imagenes

def guardar_video_en_bd(final_video_filename, guion, video_imagenes):
    video_path = f"videos/{final_video_filename}"
    print(f"Guardando video en: static/{video_path}")  # Imprime la ruta del video guardado

    video = {
        "user_id": session['user_id'],
        "titulo": "Curso Personalizado",
        "descripcion": guion[:200],
        "script": guion,
        "video_path": video_path,
        "imagen": video_imagenes.replace("static/", "")
    }

    # Verifica si el archivo realmente se ha guardado
    if not os.path.exists(os.path.join('static', video_path)):
        print(f"¡Error! El archivo {video_path} no se ha encontrado en static/videos/.")

    vids.insert_one(video)
    flash("Curso generado exitosamente 🎉", "success")

if __name__ == '__main__':
    app.run(debug=True)
