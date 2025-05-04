import os
import time
import subprocess
from subprocess import DEVNULL
import math
import logging
import hashlib
from datetime import datetime
import bcrypt
import requests
from flask import Flask, render_template, request, redirect, url_for, flash, session, jsonify
from pydub import AudioSegment
from gtts import gTTS
import openai
from openai.error import RateLimitError, InvalidRequestError, APIError
import re
import json
from pymongo import MongoClient
from config import OPENAI_API_KEY, GOOGLE_SEARCH_API_KEY, GOOGLE_SEARCH_CSE_ID
from googleapiclient.discovery import build
from bson import ObjectId
from modelo import (
    create_course,
    add_lessons_to_course,
    mark_course_completed,
    get_user_courses,
    create_video,
    get_course_videos
)

# ——— Configuración de Flask ———
app = Flask(__name__, static_folder='static', template_folder='templates')
app.secret_key = os.getenv('FLASK_SECRET', 'supersecret')
app.config['TEMPLATES_AUTO_RELOAD'] = True

# Logger
logging.getLogger('werkzeug').setLevel(logging.DEBUG)

# API Keys
openai.api_key = OPENAI_API_KEY

# MongoDB
db = MongoClient(os.getenv('MONGODB_URI', 'mongodb://localhost:27017/tfg_db')).tfg_db
users, prefs, vids = db.usuarios, db.respuestas, db.videos

# Asegurar carpetas
for d in ('static/audios', 'static/imagenes', 'static/videos'):
    os.makedirs(d, exist_ok=True)

# —— Helpers ——

def user_has_open_course(user_id):
    """
    Devuelve True si tiene un curso no completado
    **distinto** del inicial, para permitir crear el personalizado.
    """
    cursos = get_user_courses(user_id)
    for c in cursos:
        if not c.get('completed', False) and c.get('origin') != 'initial':
            return True
    return False

def fact_check_claim(texto: str) -> list[dict]:
    # Stub de fact-checking
    return []

def google_search(query: str, num_results: int = 3) -> list:
    """
    Busca en Google Custom Search (RAG). 
    Si query está vacío, devuelve lista vacía.
    Captura errores de HttpError y devuelve lista vacía.
    """
    query = (query or "").strip()
    if not query:
        logging.warning("⚠️ google_search: Query vacía, devuelvo []")
        return []

    logging.debug(f"🔍 google_search: q={query!r}, num={num_results}")

    try:
        service = build('customsearch', 'v1', developerKey=GOOGLE_SEARCH_API_KEY)
        res = (service
                 .cse()
                 .list(q=query, cx=GOOGLE_SEARCH_CSE_ID, num=num_results, hl='es')
                 .execute())
        items = res.get('items', [])
        logging.debug(f"✅ google_search: {len(items)} resultados")
        return items
    except HttpError as e:
        # Si falla (404, 403, 400, etc.), lo anotamos y devolvemos vacío
        logging.error(f"❌ google_search HttpError: {e}")
        return []
def rag_generate_script(topic: str, nivel: str, objetivo: str) -> tuple[str, list]:
    # 1) Montar y ejecutar búsqueda RAG
    query = f"{topic} nivel {nivel} objetivo {objetivo}"
    fuentes = google_search(query, num_results=3)
    if not fuentes:
        return "No se encontró información para ese tema.", []

    # 2) Construir contexto a partir de title/snippet/link
    contexto = "\n\n".join(
        f"• {f['title']}\n{f.get('snippet','')}\n{f['link']}"
        for f in fuentes
    )
    app.logger.debug("=== CONTEXTO RAG ===\n" + contexto)

    # 3) Plantilla de system prompt
    system_msg = f"""
Eres un redactor profesional de guiones didácticos en español neutro.
Estilo claro y sin muletillas.

Usa SOLO esta info:
{contexto}

El estudiante desea aprender:
- Tema: {topic}
- Nivel: {nivel}
- Objetivo: {objetivo}

Divide el contenido en 4–6 secciones, cada una con un título descriptivo único.
Cada sección debe tener entre 600 y 800 palabras.
Solo texto plano.
"""
    base_messages = [{"role": "system", "content": system_msg}]

    # 4) Generar en dos tandas (1–3 y 4–6)
    all_sections: list[str] = []
    for idx, parte in enumerate(["Secciones 1–3", "Secciones 4–6"]):
        user_msg = (
            f"Genera únicamente las {parte} del guion para el curso sobre «{topic}». "
            "Mantén el formato: título descriptivo + bloque de texto (600–800 palabras)."
        )
        messages = base_messages + [{"role": "user", "content": user_msg}]
        try:
            resp = call_gpt(
                model="gpt-4",
                messages=messages,
                max_tokens=2000,
                temperature=0.3
            )
            all_sections.append(resp.choices[0].message.content.strip())
        except Exception as e:
            app.logger.error(f"Error al generar parte {idx+1}: {e}")
            parcial = "\n\n".join(all_sections) or "Error al generar guion."
            # devuelvo parcial + fuentes para no romper el unpack
            return parcial, fuentes

    guion = "\n\n".join(all_sections)
    return guion, fuentes


# ————— Helpers —————
def call_gpt(model: str, messages: list, **kwargs):
    max_retries = 4
    for attempt in range(max_retries):
        try:
            return openai.ChatCompletion.create(
                model=model,
                messages=messages,
                request_timeout=60,   # alarga a 60s
                **kwargs
            )
        except RateLimitError as e:
            wait = 2 ** attempt
            app.logger.warning(f"RateLimitError, retry en {wait}s…")
            time.sleep(wait)
        except Timeout as e:
            wait = 2 ** attempt
            app.logger.warning(f"Timeout tras {e}, retry en {wait}s…")
            time.sleep(wait)
        except APIError as e:
            wait = 2 ** attempt
            app.logger.error(f"APIError (500), retry en {wait}s: {e}")
            time.sleep(wait)
    raise RuntimeError("El servicio de OpenAI no está disponible. Intenta de nuevo más tarde.")


def safe_image_create(prompt: str, n: int = 1, size: str = "1024x1024"):
    """
    Retry wrapper around openai.Image.create to manejar APIError.
    """
    max_retries = 3
    for attempt in range(max_retries):
        try:
            return openai.Image.create(prompt=prompt, n=n, size=size)
        except APIError as e:
            wait = 2 ** attempt
            app.logger.warning(f"[Image.create] APIError, retry en {wait}s… {e}")
            time.sleep(wait)
    raise RuntimeError("No se pudo generar la imagen tras varios intentos.")
def limpiar_guion(texto: str) -> str:
    """Elimina Markdown, muletillas y normaliza espacios del guion"""
    texto = re.sub(r"[#\*\[\]\(\)`_]", "", texto)
    muletillas = ["pues", "este", "o sea", "entonces", "bueno"]
    for m in muletillas:
        texto = re.sub(rf"\b{m}\b", "", texto, flags=re.IGNORECASE)
    texto = re.sub(r"\n{3,}", "\n\n", texto)
    texto = re.sub(r" {2,}", " ", texto)
    return texto.strip()
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
def split_por_secciones(guion: str) -> list[tuple[str,str]]:
    """
    Divide el guion en secciones buscando títulos como
    líneas cortas sin punto final, y agrupando el texto
    siguiente hasta el próximo título.
    """
    secciones = []
    current_title = None
    current_lines = []

    for line in guion.splitlines():
        stripped = line.strip()
        if not stripped:
            continue

        # Detectamos título: 
        # – Menos de 10 palabras
        # – No acaba en punto ni en dos puntos
        # – Empieza con mayúscula
        palabras = stripped.split()
        es_titulo = (
            len(palabras) < 10 and
            not stripped.endswith('.') and
            not stripped.endswith(':') and
            palabras[0][0].isupper()
        )

        if es_titulo:
            # Si ya había un título, cerramos la sección anterior
            if current_title is not None:
                secciones.append((current_title, '\n'.join(current_lines).strip()))
            current_title = stripped
            current_lines = []
        else:
            # Si no hemos encontrado título aún, lo ponemos genérico
            if current_title is None:
                current_title = "Sección"
            current_lines.append(line)

    # Añadimos la última sección
    if current_title is not None:
        secciones.append((current_title, '\n'.join(current_lines).strip()))

    return secciones




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
        # Usamos el wrapper con retries en lugar de llamar directo a Image.create
        result = safe_image_create(prompt=prompt, n=1, size="1024x1024")
        url = result.data[0].url
    except Exception as e:
        logging.error(f"Error en safe_image_create («{prompt}»): {e}")
        fallback_path = os.path.abspath("static/imagenes/fallback.png").replace("\\", "/")
        if not os.path.exists(fallback_path):
            
            raise FileNotFoundError(f"Imagen fallback no encontrada en: {fallback_path}")
        return fallback_path

    # Guardar la imagen localmente
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
from subprocess import DEVNULL

from subprocess import DEVNULL

def generar_videos_por_seccion(guion: str, max_slides: int = 6) -> list[tuple[str,str,str,str]]:
    secciones = split_por_secciones(guion)[:max_slides]
    resultados = []

    for idx, (titulo, texto) in enumerate(secciones):
        # Si el "título" es genérico, lo saltamos
        if es_titulo(titulo):
            continue

        bloques = split_en_subbloques(texto, n=3)
        imagenes, audios, clips = [], [], []

        # Generar imagen + audio + clip temporal para cada sub-bloque
        for sub_idx, bloque in enumerate(bloques):
            if not bloque.strip():
                continue

            # 1) Prompt de imagen y descarga
            prompt     = generar_prompt_imagen(bloque)
            img_path   = generate_image(prompt, f"sec{idx}_img{sub_idx}")
            audio_path = generate_audio(bloque, f"sec{idx}_aud{sub_idx}")

            imagenes.append(img_path)
            audios.append(audio_path)

            # 2) Duración del audio
            dur = float(AudioSegment.from_file(audio_path).duration_seconds)

            # 3) Construir clip con FFmpeg
            tmp_clip = os.path.join('static', 'videos', f"tmp_sec{idx}_part{sub_idx}.mp4")
            cmd = [
                'ffmpeg', '-y',
                '-loop', '1',
                '-framerate', '1',
                '-t', str(int(dur)),
                '-i', img_path,
                '-i', audio_path,
                '-c:v', 'libx264', '-preset', 'ultrafast',
                '-c:a', 'aac', '-b:a', '192k',
                '-pix_fmt', 'yuv420p',
                '-shortest',
                tmp_clip
            ]
            subprocess.run(cmd, check=True, stdout=DEVNULL, stderr=DEVNULL)
            clips.append(tmp_clip)

        # Si no se generó **ningún** clip en esta sección, la omitimos (evita errores de concat)
        if not clips:
            app.logger.warning(f"§ Se omite sección #{idx} «{titulo}» (sin clips).")
            continue

        # 4) Crear archivo de lista para concat
        list_txt = os.path.join('static', 'videos', f"list_sec{idx}.txt")
        with open(list_txt, 'w') as f:
            for clip in clips:
                ruta = os.path.abspath(clip).replace('\\', '/')
                f.write(f"file '{ruta}'\n")

        # 5) Concatenar en el vídeo final
        final_output = os.path.join('static', 'videos', f"sec{idx}.mp4")
        subprocess.run(
            ['ffmpeg', '-y', '-f', 'concat', '-safe', '0', '-i', list_txt, '-c', 'copy', final_output],
            check=True, stdout=DEVNULL, stderr=DEVNULL
        )

        resultados.append((final_output, imagenes[0], titulo, texto))

        # 6) Limpiar temporales
        for clip in clips:
            os.remove(clip)
        os.remove(list_txt)

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
    # Antes de borrar la sesión, marcamos como completados
    # todos los cursos 'initial' pendientes
    user_id = session.get('user_id')
    if user_id:
        db.cursos.update_many(
            {
                'user_id': user_id,
                'origin': 'initial',
                'completed': False
            },
            {
                '$set': {
                    'completed': True,
                    'completed_at': datetime.utcnow()
                }
            }
        )
    session.clear()
    flash('Sesión cerrada','info')
    return redirect(url_for('home'))
@app.route('/generar_curso', methods=['POST'])
def generar_curso():
    if 'user_id' not in session:
        return redirect(url_for('login'))

    # 0) No permitir otro mientras haya uno en progreso
    if user_has_open_course(session['user_id']):
        flash("🥱 Tienes un curso en progreso. Completa o márcalo terminado antes de generar otro.", "warning")
        return redirect(url_for('dashboard'))

    # 1) Recuperar inputs
    pref = prefs.find_one({'user_id': session['user_id']})
    tema       = pref['intereses']
    objetivos  = pref['objetivos']
    experiencia= pref['experiencia']

    # 2) Generar guion + vídeos
    raw, fuentes = rag_generate_script(tema, experiencia, objetivos)
    guion   = limpiar_guion(raw)
    partes  = generar_videos_por_seccion(guion)

    # 3) Si no hay secciones, abortar
    if not partes:
        flash("⚠️ No se detectaron secciones válidas. Prueba con otros objetivos.", "danger")
        return redirect(url_for('dashboard'))

    # 4) Crear curso **después** de comprobar que sí hay vídeos
   # 4) Crear curso **después** de comprobar que sí hay vídeos
    curso_id = create_course(
        user_id    = session['user_id'],
        tema       = tema,
        objetivos  = objetivos,
        experiencia= experiencia,
        origin     = 'personalizado'
    )


    # 5) Guardar mini-lecciones
    lesson_ids = []
    for ruta, img, titulo, texto in partes:
        vid_id = create_video(
            course_id   = curso_id,
            user_id     = session['user_id'],
            titulo      = titulo,
            descripcion = texto[:200],
            script      = texto,
            video_path  = os.path.basename(ruta),
            imagen      = os.path.basename(img),
            fuentes     = fuentes
        )
        lesson_ids.append(vid_id)

    add_lessons_to_course(curso_id, lesson_ids)
    flash(f"✅ {len(partes)} mini-lecciones generadas exitosamente.", "success")
    return redirect(url_for('dashboard'))

@app.route('/calendar')
def calendar_view():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    # si quieres meter lógica extra aquí
    return render_template('calendar.html')  # crea esa plantilla
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

    messages = [
        {"role": "system", "content": "Eres un asistente de ayuda amigable y experto."},
        {"role": "user",   "content": user_msg}
    ]
    try:
        resp = call_gpt(
            model="gpt-4",
            messages=messages,
            max_tokens=300,
            temperature=0.7
        )
        bot_msg = resp.choices[0].message.content.strip()
    except Exception as e:
        app.logger.error(f"Error en OpenAI Chat: {e}")
        bot_msg = "Lo siento, algo ha fallado en el servidor. Intenta de nuevo más tarde."

    return jsonify({"respuesta": bot_msg})


@app.route('/quiz_global', methods=['GET','POST'])
def quiz_global():
    # 1) Si es POST procesamos las respuestas
    if request.method == 'POST':
        preguntas = session.get('quiz_preguntas', [])
        if not preguntas:
            flash("El quiz ha expirado, por favor recárgalo.", "warning")
            return redirect(url_for('quiz_global'))

        respuestas = []
        aciertos = 0

        for idx, p in enumerate(preguntas):
            # Recuperamos la letra seleccionada (p0, p1, …)
            letra_sel = request.form.get(f'p{idx}')
            sel_idx = ord(letra_sel) - ord('A')  # de 'A'->0, 'B'->1…

            correct_idx = p['correcta']
            acertada = (sel_idx == correct_idx)
            if acertada:
                aciertos += 1

            respuestas.append({
                'pregunta': p['pregunta'],
                'opciones': p['opciones'],
                'correcta': correct_idx,
                'seleccion': sel_idx,
                'acertada': acertada
            })

        total = len(preguntas)
        return render_template('quiz_resultado.html',
                               respuestas=respuestas,
                               aciertos=aciertos,
                               total=total)

    # 2) Si es GET generamos las preguntas por primera vez
    #    Concatenamos todo el script:
    textos = [v['script'] for v in vids.find({'user_id': session['user_id']})]
    texto_completo = "\n\n".join(textos)

    system = "Eres un generador de quices. Solo responde con JSON válido."
    user = f"""
Genera 5 preguntas tipo test sobre este contenido:
\"\"\"{texto_completo}\"\"\"

Formato **exacto**:
{{
  "preguntas": [
    {{
      "pregunta": "…",
      "opciones": ["Opción A", "Opción B", "Opción C", "Opción D"],
      "correcta": 0
    }},
    … 5 en total
  ]
}}
"""
    resp = call_gpt("gpt-4", messages=[
        {"role":"system", "content": system},
        {"role":"user",   "content": user}
    ], temperature=0.3)

    try:
        data = json.loads(resp.choices[0].message.content)
    except Exception:
        flash("No pude parsear el quiz. Aquí tienes el texto crudo:", "warning")
        return render_template('quiz_error.html', raw=resp.choices[0].message.content)

    preguntas = data['preguntas']
    # Guardamos en session para usar en el POST
    session['quiz_preguntas'] = preguntas

    return render_template('quiz_global.html', preguntas=preguntas)

@app.route('/dashboard')
def dashboard():
    # 1) Asegurarnos de que está logueado
    if 'user_id' not in session:
        return redirect(url_for('login'))

    # 2) Recuperar datos de usuario y cursos
    usuario = session['usuario']
    cursos  = get_user_courses(session['user_id'])
    print(f"[DEBUG] Cursos recuperados para {usuario}: {cursos}")

        # 3) Para cada curso, inyectar la lista de vídeos generados
    for curso in cursos:
        curso['lecciones_detalle'] = get_course_videos(curso['_id'])

    # 4) Renderizar plan tilla con dos variables:
    #    - usuario: nombre a mostrar
    #    - mis_cursos: lista completa de cursos
    return render_template(
        'dashboard.html',
        usuario=usuario,
        mis_cursos=cursos
    )
@app.route('/solicitar_curso', methods=['GET','POST'])
def solicitar_curso():
    if 'user_id' not in session:
        return redirect(url_for('login'))

    if request.method == 'POST':
        # 0) Mismo chequeo de “en progreso”:
        if user_has_open_course(session['user_id']):
            flash("🥱 Ya tienes un curso en progreso, termínalo antes.", "warning")
            return redirect(url_for('dashboard'))

        # 1) Leer formulario
        tema        = request.form['tema']
        objetivos   = request.form['objetivos']
        experiencia = request.form['experiencia']

        # 2) Generar guion + vídeos
        raw, fuentes = rag_generate_script(tema, experiencia, objetivos)
        guion   = limpiar_guion(raw)
        partes  = generar_videos_por_seccion(guion)
        if not partes:
            flash("⚠️ No se detectaron secciones para ese tema. Inténtalo con otros parámetros.", "danger")
            return redirect(url_for('solicitar_curso'))

        # 3) Crear curso y guardar lecciones
        curso_id = create_course(
            user_id    = session['user_id'],
            tema       = tema,
            objetivos  = objetivos,
            experiencia= experiencia
        )
        lesson_ids = []
        for ruta, img, titulo, texto in partes:
            vid_id = create_video(
                course_id   = curso_id,
                user_id     = session['user_id'],
                titulo      = titulo,
                descripcion = texto[:200],
                script      = texto,
                video_path  = os.path.basename(ruta),
                imagen      = os.path.basename(img),
                fuentes     = fuentes
            )
            lesson_ids.append(vid_id)
        add_lessons_to_course(curso_id, lesson_ids)

        flash("🎉 Curso solicitado y mini-lecciones generadas.", "success")
        return redirect(url_for('dashboard'))

    return render_template('solicitar_curso.html', usuario=session['usuario'])


@app.route('/cursos/<curso_id>/complete', methods=['POST'])
def complete_curso(curso_id):
    oid = ObjectId(curso_id)
    mark_course_completed(oid)
    flash("Curso marcado como completado ✅", "success")
    return redirect(url_for('dashboard'))


@app.route('/mis_cursos')
def mis_cursos_view():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    usuario    = session['usuario']
    cursos     = get_user_courses(session['user_id'])
    for c in cursos:
        c['lecciones_detalle'] = get_course_videos(c['_id'])
    return render_template('mis_cursos.html',
                           usuario=usuario,
                           mis_cursos=cursos)
@app.route('/generar_curso_inicial', methods=['POST'])
def generar_curso_inicial():
    if 'user_id' not in session:
        return redirect(url_for('login'))

    if user_has_open_course(session['user_id']):
        flash("🥱 Ya tienes un curso inicial creado.", "warning")
        return redirect(url_for('dashboard'))

    pref = prefs.find_one({'user_id': session['user_id']})
    tema = pref['intereses']
    objetivos = pref['objetivos']
    experiencia = pref['experiencia']

    raw, fuentes = rag_generate_script(tema, experiencia, objetivos)
    guion = limpiar_guion(raw)
    partes = generar_videos_por_seccion(guion)

    if not partes:
        flash("⚠️ No se detectaron secciones. Contacta al soporte.", "danger")
        return redirect(url_for('dashboard'))

    curso_id = create_course(
        user_id=session['user_id'],
        tema=tema,
        objetivos=objetivos,
        experiencia=experiencia,
        origin='initial'  # Indicamos claramente que es curso inicial
    )

    lesson_ids = []
    for ruta, img, titulo, texto in partes:
        vid_id = create_video(
            course_id=curso_id,
            user_id=session['user_id'],
            titulo=titulo,
            descripcion=texto[:200],
            script=texto,
            video_path=os.path.basename(ruta),
            imagen=os.path.basename(img),
            fuentes=fuentes
        )
        lesson_ids.append(vid_id)

    add_lessons_to_course(curso_id, lesson_ids)

    flash("🎉 Tu curso inicial está listo!", "success")
    return redirect(url_for('dashboard', _anchor='cursos'))
@app.route('/generar_curso_personalizado', methods=['POST'])
def generar_curso_personalizado():
    if 'user_id' not in session:
        return redirect(url_for('login'))

    # No permitir otro curso si ya hay uno en progreso
    if user_has_open_course(session['user_id']):
        flash("🥱 Termina tu curso actual antes de solicitar uno nuevo.", "warning")
        return redirect(url_for('dashboard'))

    # Leer datos del formulario
    tema = request.form.get('tema', '').strip()
    objetivos = request.form.get('objetivos', '').strip()
    experiencia = request.form.get('experiencia', '').strip()

    # Validar formulario
    if not tema or not objetivos or not experiencia:
        flash("Por favor, completa todos los campos del formulario.", "warning")
        return redirect(url_for('dashboard', _anchor='nuevos'))

    # Generar guion y vídeos
    raw, fuentes = rag_generate_script(tema, experiencia, objetivos)
    guion = limpiar_guion(raw)
    partes = generar_videos_por_seccion(guion)

    # Si no hay secciones, abortar
    if not partes:
        flash("⚠️ No se detectaron secciones válidas para ese tema. Prueba con otros parámetros.", "danger")
        return redirect(url_for('dashboard', _anchor='nuevos'))

    # Crear el curso en la base de datos
    curso_id = create_course(
        user_id=session['user_id'],
        tema=tema,
        objetivos=objetivos,
        experiencia=experiencia,
        origin='personalizado'
    )

    # Guardar cada mini-lección (vídeo) en el curso
    lesson_ids = []
    for ruta, img, titulo, texto in partes:
        vid_id = create_video(
            course_id=curso_id,
            user_id=session['user_id'],
            titulo=titulo,
            descripcion=texto[:200],
            script=texto,
            video_path=os.path.basename(ruta),
            imagen=os.path.basename(img),
            fuentes=fuentes
        )
        lesson_ids.append(vid_id)

    # Asignar las lecciones al curso
    add_lessons_to_course(curso_id, lesson_ids)

    flash("🎉 Tu curso personalizado ha sido generado con éxito!", "success")
    return redirect(url_for('dashboard', _anchor='cursos'))

if __name__ == '__main__':
    app.run(debug=True)