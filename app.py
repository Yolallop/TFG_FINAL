from flask import Flask, render_template, request, redirect, url_for, flash, session
import logging
import os
import openai
import bcrypt
import requests
from pathlib import Path
from gtts import gTTS
import time
app = Flask(__name__, static_folder='static', template_folder='templates')

import subprocess
import config 
# Configuración de APIs
from app_gtts_final import generar_video_completo  # Asegúrate de tener este archivo o adaptar las funciones necesarias
from config import OPENAI_API_KEY

openai.api_key = OPENAI_API_KEY
from pymongo import MongoClient
client = MongoClient("mongodb://localhost:27017")

# Configuración de Flask
app = Flask(__name__, template_folder='templates', static_folder='static')
app.config['TEMPLATES_AUTO_RELOAD'] = True
app.jinja_env.auto_reload = True
app.debug = True
app.secret_key = 'clave_super_secreta'

# MongoDB
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

        prefs.replace_one({"user_id": session['user_id']}, nueva_respuesta, upsert=True)
        return redirect(url_for('dashboard'))

    return render_template('preguntas.html')

@app.route('/evaluacion')
def evaluacion():
    return render_template('evaluacion.html')

@app.route("/chatbot", methods=["POST", "GET"])
def chatbot():
    user_profile = {
        'name': session['name'],
        'last_name': session['last_name'],
        'status': session['status']
    }

    if request.method == 'POST':
        user_message = request.form["msg"]
        response = openai.Completion.create(
            model="gpt-3.5-turbo",
            prompt=prompt,
            max_tokens=500
        )


        bot_response = response.choices[0].text.strip()

        return render_template('chatbot.html', bot_response=bot_response, user_profile=user_profile)
    else:
        return render_template('chatbot.html', user_profile=user_profile)

import time
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

    # Obtener preferencias del usuario
    respuestas = prefs.find_one({"user_id": session['user_id']})
    if not respuestas:
        flash("Debes completar el formulario de preferencias primero.", "warning")
        return redirect(url_for('preguntas'))

    # Generar el guion (script)
    guion = generar_guion_dinamico(respuestas)
    print(f"Guion: {guion}")

    # Generar las rutas de los videos y las imágenes
    max_videos = 3
    ruta_video, video_imagenes = generar_video_completo(guion, max_videos)
    print(f"Video Path: {ruta_video}")
    print(f"Imagenes Path: {video_imagenes}")

    if not guion or not ruta_video or not video_imagenes:
        flash("Hubo un problema al generar el curso, intenta nuevamente.", "danger")
        return redirect(url_for('dashboard'))

    # Verificar si video_imagenes es una lista y tomar el primer valor si es necesario
    if isinstance(video_imagenes, list):
        video_imagenes = video_imagenes[0]  # Tomar la primera imagen de la lista

    # Generar un nombre de video único
    timestamp = int(time.time())  # Usamos el timestamp para asegurar un nombre único
    video_filename = f"video_{timestamp}.mp4"  # Nombre único del archivo de video

    # Insertar en la base de datos
    video = {
        "user_id": session['user_id'],
        "titulo": "Curso Personalizado",
        "descripcion": guion[:200],  # Solo los primeros 200 caracteres de la descripción
        "script": guion,
        "video_path": f"videos/{video_filename}",
        "imagen": video_imagenes.replace("static/", "")  # Aseguramos que la ruta sea correcta
    }

    # Guardar el video en la base de datos
    vids.insert_one(video)

    flash("Curso generado exitosamente 🎉", "success")
    return redirect(url_for('dashboard'))  # Redirigir al dashboard después de generar el curso


def generar_video_completo(guion, max_videos):
    scenes = guion.split("\n\n")
    video_parts = []
    video_imagenes = []  # Cambiado a una lista para guardar las imágenes generadas
    max_videos = min(max_videos, len(scenes))

    for idx, scene in enumerate(scenes[:max_videos]):
        prompt = f"Genera una imagen para: {scene}"
        image_path = generate_image(prompt, idx)
        audio_path = generate_audio(scene, idx)

        # Asegúrate de que la ruta de los videos sea correcta
        video_path = os.path.join("static/videos", f"video_{idx}.mp4")
        video_parts.append(video_path)
        generar_video_con_ffmpeg(image_path, audio_path, video_path)

        video_imagenes.append(image_path)  # Guardar la imagen correspondiente

    final_video_path = "static/videos/final_video.mp4"
    combine_videos(video_parts, final_video_path)

    return final_video_path, video_imagenes  # Devuelve la ruta final y las imágenes generadas
import os
import subprocess

def combine_videos(video_parts, output_video):
    # Verificar si los archivos de video existen
    for video in video_parts:
        if not os.path.exists(video):
            raise FileNotFoundError(f"El archivo {video} no se encuentra.")

    # Comando FFmpeg simple para concatenar los videos
    inputs = " ".join([f"-i \"{os.path.abspath(video)}\"" for video in video_parts])
    output_video = os.path.abspath(output_video)

    # Comando de concatenación de videos (sin filtro complejo)
    command = f"ffmpeg {inputs} -c copy {output_video}"

    print(f"Comando generado: {command}")

    try:
        # Ejecutar el comando FFmpeg
        result = subprocess.run(command, shell=True, check=True, stderr=subprocess.PIPE, stdout=subprocess.PIPE)
        
        # Mostrar la salida y el error de FFmpeg
        print(f"Salida de FFmpeg: {result.stdout.decode()}")
        print(f"Error de FFmpeg: {result.stderr.decode()}")
        
        print(f"Videos combinados en: {output_video}")
    
    except subprocess.CalledProcessError as e:
        print(f"Error en FFmpeg: {e.stderr.decode()}")
        raise

    except FileNotFoundError as e:
        print(f"Error: {e}")
        raise

    except Exception as e:
        print(f"Error inesperado: {e}")
        raise

# Esta función genera el guion personalizado en base a las respuestas
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

# Generación de imagen y audio
from pydub.utils import mediainfo

def get_audio_duration(audio_path):
    # Get the audio file's information
    info = mediainfo(audio_path)
    # Return the duration in seconds
    return float(info['duration'])

def generate_image(prompt, id):
    try:
        # Crear la imagen usando OpenAI
        result = openai.Image.create(
            prompt=prompt,
            n=1,  # Número de imágenes a generar
            size="1024x1024"  # Tamaño de la imagen
        )

        image_url = result['data'][0]['url']  # Obtener la URL de la imagen generada
        image_path = os.path.join("static/imagenes", f"{id}.png")  # Ruta donde se guardará la imagen

        # Intentar descargar la imagen hasta 3 veces en caso de que ocurra un error temporal
        for attempt in range(3):
            response = requests.get(image_url, timeout=30)  # Timeout de 30 segundos para la solicitud
            if response.status_code == 200:
                # Guardar la imagen en la carpeta estática
                with open(image_path, "wb") as f:
                    f.write(response.content)
                print(f"Imagen guardada en: {image_path}")
                return image_path  # Retornar la ruta de la imagen

            # Si la respuesta no es exitosa, reintentar después de un pequeño retraso
            print(f"Error al descargar la imagen (Intento {attempt + 1}/3): {response.status_code}")
            sleep(2)

        # Si llegamos aquí es porque los intentos fallaron
        print("No se pudo descargar la imagen después de 3 intentos.")
        return None

    except Exception as e:
        # Si ocurre algún otro error, se captura y se muestra
        print(f"Error inesperado al generar o guardar la imagen: {e}")
        return None


def generate_audio(texto, id):
    audio_file = os.path.join("static/audios", f"{id}.mp3")
    
    # Generar el audio con gTTS (puedes cambiar el idioma si es necesario)
    tts = gTTS(text=texto, lang='es')  # 'es' es para español. Puedes cambiarlo a otros idiomas como 'en' para inglés
    
    # Guardar el archivo de audio generado
    tts.save(audio_file)
    
    return audio_file

        
def generar_video_con_ffmpeg(imagen, audio, output_video):
    try:
        # Verifica que la imagen y el audio existen antes de proceder
        if not os.path.exists(imagen):
            raise FileNotFoundError(f"La imagen {imagen} no se encuentra.")
        if not os.path.exists(audio):
            raise FileNotFoundError(f"El audio {audio} no se encuentra.")
        
        # Obtener la duración del audio
        audio_duration = get_audio_duration(audio)  # Obtener duración del audio
        command = [
            'ffmpeg', '-y', '-loop', '1', '-framerate', '2', '-t', str(audio_duration),
            '-i', imagen, '-i', audio, '-c:v', 'libx264', '-preset', 'veryfast',
            '-c:a', 'aac', '-b:a', '192k', '-pix_fmt', 'yuv420p', '-shortest', output_video
        ]   

        
        # Ejecutar el comando y revisar si hubo algún error
        subprocess.run(command, check=True)
        print(f"Video generado correctamente en: {output_video}")
    
    except FileNotFoundError as e:
        print(f"Error: {e}")
    except subprocess.CalledProcessError as e:
        print(f"Error en FFmpeg: {e}")
    except Exception as e:
        print(f"Error inesperado: {e}")


if __name__ == '__main__':
    app.run(debug=True)