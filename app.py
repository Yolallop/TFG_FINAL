import re
import os
import time
import subprocess
import math
import random
import logging
import requests
import bcrypt
from flask import Flask, render_template, request, redirect, url_for, flash, session, jsonify
from pydub import AudioSegment
from pydub.utils import mediainfo
from gtts import gTTS
import openai
from openai.error import RateLimitError, InvalidRequestError

from pymongo import MongoClient
from config import OPENAI_API_KEY

# Configuración de Flask
tmp = os.path.dirname(__file__)
app = Flask(__name__, static_folder='static', template_folder='templates')
app.secret_key = 'clave_super_secreta'
app.config['TEMPLATES_AUTO_RELOAD'] = True
app.jinja_env.auto_reload = True
app.debug = True

# Logger
log = logging.getLogger('werkzeug')
log.setLevel(logging.DEBUG)

# API Key OpenAI
openai.api_key = OPENAI_API_KEY

# MongoDB
db_client = MongoClient(os.getenv('MONGODB_URI', 'mongodb://localhost:27017/tfg_db'))
db = db_client.tfg_db
users = db.usuarios
prefs = db.respuestas
vids  = db.videos

# Crear carpetas estáticas
os.makedirs('static/audios', exist_ok=True)
os.makedirs('static/imagenes', exist_ok=True)
os.makedirs('static/videos', exist_ok=True)

# ————— Helpers —————
def split_por_secciones(guion: str):
    """Divide el guion en secciones por doble salto de línea."""
    bloques = [b.strip() for b in guion.split("\n\n") if len(b.strip()) > 30]
    resultado = []
    for idx, bloque in enumerate(bloques):
        lineas = bloque.split("\n", 1)
        if len(lineas) == 2:
            titulo, contenido = lineas
        else:
            titulo = f"Sección {idx+1}"
            contenido = bloque
        resultado.append((titulo.strip(), contenido.strip()))
    return resultado



def limpiar_guion(texto: str) -> str:
    """Elimina Markdown, muletillas y normaliza espacios del guion"""
    texto = re.sub(r"[#\*\[\]\(\)`_]", "", texto)
    muletillas = ["pues", "este", "o sea", "entonces", "bueno"]
    for m in muletillas:
        texto = re.sub(rf"\b{m}\b", "", texto, flags=re.IGNORECASE)
    texto = re.sub(r"\n{3,}", "\n\n", texto)
    texto = re.sub(r" {2,}", " ", texto)
    return texto.strip()


def call_gpt(model: str, messages: list, **kwargs):
    """Llamadas a ChatCompletion con back-off ante RateLimitError"""
    for attempt in range(3):
        try:
            return openai.ChatCompletion.create(model=model, messages=messages, **kwargs)
        except RateLimitError:
            wait = 2 ** attempt
            logging.warning(f"RateLimitError en call_gpt, reintento en {wait}s")
            time.sleep(wait)
    raise

def generar_guion_dinamico(respuestas: dict) -> str:
    nivel = respuestas['experiencia']
    tema = respuestas['intereses']
    objetivo = respuestas['objetivos']
    prompt = f"""
Eres un profesor experto. El estudiante desea aprender:
- Tema: {tema}
- Nivel: {nivel}
- Objetivo: {objetivo}

Por favor, entrega un guion detallado y dividido en 4 a 6 secciones. 
Cada sección debe tener un título DESCRIPTIVO y único (por ejemplo: "Estrategias de Marketing Digital en Redes Sociales", NO pongas "Sección 1").
Después del título, escribe un contenido de 600 a 800 palabras con ejemplos reales.

Formato solicitado:
**Título de la sección**
Contenido extenso aquí...

IMPORTANTE:
- No uses "Sección 1", "Sección 2", ni números.
- No pongas marcas de Markdown excepto los títulos (**) si quieres.
- Cada sección debe ser AUTÓNOMA y tener sentido por sí misma.
- Solo texto plano. No añadas bullets, tablas ni listas.
    """
    resp = call_gpt(
        model="gpt-4",
        messages=[
            {"role":"system","content":"Eres un profesor universitario experto en enseñar de forma clara."},
            {"role":"user","content":prompt}
        ],
        max_tokens=6000,
        temperature=0.5
    )
    return resp.choices[0].message.content.strip()

def generar_prompt_imagen(texto: str) -> str:
    resumen = f"Resumen del contenido: {texto[:500]}"  # Hasta 500 caracteres para mejor contexto
    prompt_mejorado = f"Genera un prompt visual de 10-15 palabras que represente este contenido de programación:\n{resumen}"
    
    for intento in range(3):
        try:
            resp = openai.ChatCompletion.create(
                model="gpt-3.5-turbo",
                messages=[
                    {"role":"system","content":"Eres un experto en generar prompts para imágenes educativas."},
                    {"role":"user","content":prompt_mejorado}
                ],
                max_tokens=50,
                temperature=0.7
            )
            return resp.choices[0].message.content.strip()
        except RateLimitError:
            wait = 2 ** intento
            logging.warning(f"RateLimitError en generar_prompt_imagen, intento {intento+1}")
            time.sleep(wait)
        except InvalidRequestError as e:
            logging.error(f"InvalidRequestError en generar_prompt_imagen: {e}")
            break

    return "Representación visual de programación de Python, estilo moderno, claro"


def generate_image(prompt: str, id: str) -> str:
    logging.debug(f"[generate_image] prompt: {prompt}")
    try:
        result = openai.Image.create(prompt=prompt, n=1, size="1024x1024")
        url = result.data[0].url
    except InvalidRequestError as e:
        logging.error(f"Error en Image.create («{prompt}»): {e}")
        return os.path.abspath("static/imagenes/fallback.png")
    carpeta = os.path.abspath("static/imagenes").replace("\\","/")
    os.makedirs(carpeta, exist_ok=True)
    path = f"{carpeta}/{id}.png"
    try:
        r = requests.get(url, timeout=30)
        r.raise_for_status()
        with open(path, 'wb') as f:
            f.write(r.content)
    except Exception as e:
        logging.error(f"No se pudo descargar la imagen de {url}: {e}")
        return os.path.abspath("static/imagenes/fallback.png")
    return path


def generate_audio(texto: str, id: str) -> str:
    path = os.path.join('static/audios', f"{id}.mp3")
    gTTS(texto, lang='es').save(path)
    return path


def split_en_subbloques(texto: str, n: int) -> list[str]:
    frases = re.split(r'(?<=[\.!?])\s+', texto.strip())
    chunk = math.ceil(len(frases)/n)
    return [' '.join(frases[i*chunk:(i+1)*chunk]) for i in range(n)]

import random  # 👈 no olvides importar esto arriba

def generar_videos_por_seccion(guion: str, max_slides: int = 6, min_duration: int = 180, max_duration: int = 300) -> list[tuple[str,str,str,str]]:
    secciones = split_por_secciones(guion)[:max_slides]
    resultados = []

    for idx, (titulo, texto) in enumerate(secciones):
        if es_titulo(titulo):
            print(f"🔵 Título detectado (no genera video): {titulo}")
            continue

        bloques = split_en_subbloques(texto, n=5)  # Dividimos en 5 partes

        imagenes = []
        audios = []
        clips = []

        for sub_idx, bloque in enumerate(bloques):
            if bloque.strip():
                prompt = generar_prompt_imagen(bloque)
                img_path = generate_image(prompt, f"sec{idx}_img{sub_idx}")
                aud_path = generate_audio(bloque, f"sec{idx}_aud{sub_idx}")
                imagenes.append(img_path)
                audios.append(aud_path)

                # Crear un clip para cada imagen+audio
                duracion = float(AudioSegment.from_file(aud_path).duration_seconds)
                out_tmp = os.path.join('static', 'videos', f"tmp_sec{idx}_part{sub_idx}_{int(time.time())}.mp4")
                cmd = [
                    'ffmpeg', '-y', '-loop', '1', '-framerate', '1',
                    '-t', str(int(duracion)),
                    '-i', img_path,
                    '-i', aud_path,
                    '-c:v', 'libx264', '-preset', 'veryfast',
                    '-c:a', 'aac', '-b:a', '192k',
                    '-pix_fmt', 'yuv420p', '-shortest', out_tmp
                ]
                subprocess.run(cmd, check=True)
                clips.append(out_tmp)

        # Concatenar los mini videos en uno solo
        list_file = os.path.join('static', 'videos', f"list_sec{idx}.txt")
        with open(list_file, 'w') as f:
            for clip in clips:
                f.write(f"file '{os.path.abspath(clip).replace('\\\\','/')}'\n")

        final_output = os.path.join('static', 'videos', f"sec{idx}_{int(time.time())}.mp4")
        cmd_concat = [
            'ffmpeg', '-y', '-f', 'concat', '-safe', '0', '-i', list_file,
            '-c', 'copy', final_output
        ]
        subprocess.run(cmd_concat, check=True)

        resultados.append((final_output, imagenes[0], titulo, texto))

        # Limpiar temporales
        for clip in clips:
            os.remove(clip)
        os.remove(list_file)

    return resultados

def es_titulo(texto: str) -> bool:
    palabras = texto.lower().split()
    palabras_titulo = ["introducción", "conclusión", "presentación", "inicio", "final", "resumen"]
    return any(palabra in palabras for palabra in palabras_titulo) or len(palabras) < 5

# ————— Rutas Flask —————

@app.route('/')
def home():
    return render_template('index.html')

@app.route('/register', methods=['GET','POST'])
def register():
    if request.method=='POST':
        nombre = request.form['nombre'].strip()
        email  = request.form['email'].lower().strip()
        pwd    = request.form['password'].encode('utf-8')
        if users.find_one({'email':email}):
            flash('Correo ya registrado','danger')
            return redirect(url_for('register'))
        hashed = bcrypt.hashpw(pwd, bcrypt.gensalt())
        users.insert_one({'nombre':nombre,'email':email,'password':hashed})
        u = users.find_one({'email':email})
        session['user_id']=str(u['_id'])
        session['usuario']=nombre
        return redirect(url_for('preguntas'))
    return render_template('register.html')

@app.route('/login', methods=['GET','POST'])
def login():
    if request.method=='POST':
        email = request.form['email'].lower().strip()
        pwd   = request.form['password'].encode('utf-8')
        u = users.find_one({'email':email})
        if u and bcrypt.checkpw(pwd, u['password']):
            session['user_id']=str(u['_id'])
            session['usuario']=u['nombre']
            return redirect(url_for('dashboard'))
        flash('Credenciales incorrectas','danger')
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.clear()
    flash('Sesión cerrada','info')
    return redirect(url_for('home'))

@app.route('/preguntas', methods=['GET','POST'])
def preguntas():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    if request.method=='POST':
        intereses = ','.join(request.form.getlist('intereses'))
        objetivos = request.form['objetivos']
        experiencia = request.form['experiencia']
        prefs.replace_one({'user_id':session['user_id']}, {'user_id':session['user_id'],'intereses':intereses,'objetivos':objetivos,'experiencia':experiencia}, upsert=True)
        return redirect(url_for('dashboard'))
    return render_template('preguntas.html')

@app.route('/chat', methods=['POST'])
def chat():
    if 'user_id' not in session:
        return jsonify({'respuesta':'Por favor, inicia sesión primero.'}), 401

    user_msg = request.form.get('msg','').strip()
    if not user_msg:
        return jsonify({'respuesta':'Escribe algo para que pueda ayudarte.'})

    try:
        response = openai.ChatCompletion.create(
            model="gpt-4",
            messages=[
                {"role": "system", "content": "Eres un asistente de ayuda amigable y experto."},
                {"role": "user",   "content": user_msg}
            ],
            max_tokens=300,
            temperature=0.7
        )
        bot_msg = response.choices[0].message.content.strip()
    except Exception as e:
        app.logger.error(f"Error en OpenAI Chat: {e}")
        bot_msg = "Lo siento, algo ha fallado en el servidor."

    return jsonify({"respuesta": bot_msg})


@app.route('/dashboard')
def dashboard():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    usuario     = session['usuario']
    respuestas  = prefs.find_one({'user_id':session['user_id']})
    videos_list = list(vids.find({'user_id':session['user_id']}))
    for v in videos_list:
        path = os.path.join('static','videos',v['video_path'])
        if not os.path.exists(path):
            flash(f"Falta {v['video_path']}",'danger')
    return render_template('dashboard.html',usuario=usuario,respuestas=respuestas,videos=videos_list)

@app.route('/generar_curso', methods=['POST'])
def generar_curso():
    pref = prefs.find_one({'user_id': session['user_id']})
    if not pref:
        flash('Completa preferencias.', 'warning')
        return redirect(url_for('preguntas'))

    raw = generar_guion_dinamico(pref)
    guion = limpiar_guion(raw)
    partes = generar_videos_por_seccion(guion)

    # 🛡️ PROTECCIÓN nueva aquí:
    if not partes:
        flash("No se pudo generar el curso porque no se detectaron secciones válidas.", "danger")
        return redirect(url_for('dashboard'))

    # Si hay partes, se guardan normalmente:
    for ruta, img, titulo, texto in partes:
        if ':' in titulo:
            display_title = titulo.split(':',1)[1].strip()
        else:
            display_title = titulo
        vids.insert_one({
            'user_id': session['user_id'],
            'titulo': display_title,
            'descripcion': texto[:200],
            'script': texto,
            'video_path': os.path.basename(ruta),
            'imagen': os.path.basename(img)
        })

    flash(f"{len(partes)} mini-lecciones generadas 🎉", 'success')
    return redirect(url_for('dashboard'))


if __name__ == '__main__':
    app.run(debug=True)


