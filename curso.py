from flask import Flask, render_template, request, redirect, url_for, flash, session
from pymongo import MongoClient
from config import OPENAI_API_KEY, ELEVEN_API_KEY
import logging
import os
import openai
import subprocess
from gtts import gTTS
from PIL import Image
import base64

from elevenlabs import generate, save, set_api_key

set_api_key(ELEVEN_API_KEY)



# Configuración de OpenAI
openai.api_key = OPENAI_API_KEY

# Configuración de logging
logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

# Configuración de Flask y MongoDB
app = Flask(__name__, template_folder='templates', static_folder='static')
app.config['TEMPLATES_AUTO_RELOAD'] = True
app.jinja_env.auto_reload = True
app.debug = True
app.secret_key = 'clave_super_secreta'  # Cambia esto por algo más seguro

# Asegúrate de definir la variable 'text' antes de usarla
text = "Este es el texto que quiero convertir a voz."  # Asegúrate de definirlo

# Usamos el método correcto para generar el audio
audio = eleven.text_to_speech(text)  # Usando el método correcto para generar el audio

# Guardamos el archivo de audio generado
audio_path = 'static/audios/curso_audio.mp3'
with open(audio_path, 'wb') as f:
    f.write(audio)

# Asegúrate de que MongoDB está configurado correctamente
mongo = MongoClient("mongodb://localhost:27017")
db = mongo.tfg_db
users = db.usuarios
prefs = db.respuestas
vids = db.videos

# Directorios para guardar archivos generados
aud_dir = os.path.join("static", "audios")
img_dir = os.path.join("static", "imagenes")
vid_dir = os.path.join("static", "videos")
os.makedirs(aud_dir, exist_ok=True)
os.makedirs(img_dir, exist_ok=True)
os.makedirs(vid_dir, exist_ok=True)


@app.route('/')
def home():
    return render_template('index.html')


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


@app.route('/logout')
def logout():
    session.clear()
    flash("Sesión cerrada", "info")
    return redirect(url_for('home'))


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

        prefs.replace_one(
            {"user_id": session['user_id']},
            nueva_respuesta,
            upsert=True
        )

        return redirect(url_for('dashboard'))

    return render_template('preguntas.html')


@app.route('/dashboard')
def dashboard():
    if 'user_id' not in session:
        return redirect(url_for('login'))

    usuario = session['usuario']
    respuestas = prefs.find_one({"user_id": session['user_id']})
    videos = vids.find({"user_id": session['user_id']})

    return render_template('dashboard.html', usuario=usuario, respuestas=respuestas, videos=videos)


@app.route('/generar_curso', methods=['POST'])
def generar_curso():
    if 'user_id' not in session:
        return redirect(url_for('login'))

    # Obtener respuestas del usuario desde MongoDB
    respuestas = prefs.find_one({"user_id": session['user_id']})

    # Validación
    if not respuestas:
        flash("Debes completar el formulario de preferencias primero.", "warning")
        return redirect(url_for('preguntas'))
    
    # 1. Generar el guion con OpenAI
    guion = generar_guion_dinamico(respuestas)

    # 2. Generar imágenes basadas en el guion
    imagenes = generar_imagenes(guion)

    # 3. Generar el audio
    ruta_audio = generar_audio_con_elevenlabs(guion)

    # 4. Crear el video
    video_path = crear_video(imagenes, ruta_audio)

    # Guardar el video en MongoDB
    video = {
        "user_id": session['user_id'],
        "titulo": "Curso Personalizado",
        "descripcion": guion[:200],
        "script": guion,
        "video_path": video_path
    }
    vids.insert_one(video)

    flash("Curso generado exitosamente", "success")
    return redirect(url_for('dashboard'))


def generar_guion_dinamico(respuestas):
    """
    Genera el guion dinámico basado en las respuestas del usuario.
    """
    prompt = f"""
    Eres un experto creando cursos online. Crea un guion para un curso sobre el tema: {respuestas['intereses']}.
    El estudiante tiene nivel {respuestas['experiencia']} y su objetivo es: {respuestas['objetivos']}.
    El guion debe tener entre 350 y 500 palabras por sección y debe ser adecuado para un video de 3 a 4 minutos de duración.
    """
    
    response = openai.Completion.create(
        engine="text-davinci-003",  # Usar el modelo de OpenAI
        prompt=prompt,
        max_tokens=500
    )
    return response.choices[0].text.strip()


def generar_imagenes(guion):
    """
    Genera imágenes usando DALL·E 3 o una alternativa con base en el guion.
    """
    prompt_imagen = f"Genera imágenes para el tema: {guion[:150]}"  # Obtener las primeras 150 palabras para el prompt
    response = openai.Image.create(
        model="dall-e-3",  # Usar el modelo DALL-E 3
        prompt=prompt_imagen,
        n=1,
        size="1024x1024",
        response_format="b64_json"
    )
    
    # Guardar la imagen en un archivo
    imagen_b64 = response['data'][0]['b64_json']
    imagen_bytes = base64.b64decode(imagen_b64)
    ruta_imagen = "static/imagenes/curso_imagen.png"
    with open(ruta_imagen, 'wb') as f:
        f.write(imagen_bytes)
    
    return ruta_imagen


def generar_audio_con_elevenlabs(guion):
    """
    Genera el audio del guion usando ElevenLabs.
    """
    audio = generate(
        text=guion,
        voice="Rachel",  # Puedes cambiar por cualquier voz disponible
        model="eleven_monolingual_v1"
    )

    ruta_audio = "static/audios/curso_audio.mp3"
    save(audio, ruta_audio)

    return ruta_audio


def crear_video(imagen_path, audio_path):
    """
    Crea un video combinando imagen y audio con FFmpeg.
    """
    output_path = "static/videos/curso_video.mp4"
    subprocess.run([
        "ffmpeg", "-y",
        "-loop", "1", "-framerate", "2",  # Ajuste para video con una sola imagen
        "-i", imagen_path,
        "-i", audio_path,
        "-c:v", "libx264", "-tune", "stillimage",
        "-c:a", "aac", "-b:a", "192k",
        "-pix_fmt", "yuv420p", "-shortest",  # El video durará lo mismo que el audio
        output_path
    ])

    return output_path


if __name__ == '__main__':
    app.run(debug=True)
