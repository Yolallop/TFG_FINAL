from flask import Flask, render_template, request, redirect, url_for, flash, session
from flask_sqlalchemy import SQLAlchemy
import bcrypt
from modelo import db, Usuario, UsuarioRespuestas, Video
from openai import OpenAI
import base64
import os
from config import OPENAI_API_KEY, ELEVEN_API_KEY
import subprocess
from PIL import Image, ImageDraw, ImageFont
import re
import elevenlabs


# Configuración de OpenAI
client = OpenAI(api_key=OPENAI_API_KEY)

app = Flask(__name__)
app.secret_key = 'clave_super_secreta'
app.config['SQLALCHEMY_DATABASE_URI'] = 'postgresql://postgres:postgres@localhost:5432/tfg_db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db.init_app(app)


@app.route('/')
def home():
    return render_template('index.html')


@app.route('/evaluacion')
def evaluacion():
    return render_template('evaluacion.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        nombre = request.form['nombre']
        email = request.form['email']
        password = request.form['password']

        if Usuario.query.filter_by(email=email).first():
            flash('El correo ya está registrado.', 'danger')
            return redirect(url_for('register'))

        hashed = bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
        nuevo_usuario = Usuario(nombre=nombre, email=email, password=hashed)

        db.session.add(nuevo_usuario)
        db.session.commit()

        session['user_id'] = nuevo_usuario.id
        session['usuario'] = nuevo_usuario.nombre

        return redirect(url_for('preguntas'))

    return render_template('register.html')


@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form['email']
        password = request.form['password'].encode('utf-8')

        usuario = Usuario.query.filter_by(email=email).first()
        if usuario and bcrypt.checkpw(password, usuario.password.encode('utf-8')):
            session['user_id'] = usuario.id
            session['usuario'] = usuario.nombre
            return redirect(url_for('dashboard'))

        flash('Credenciales incorrectas', 'danger')

    return render_template('login.html')


@app.route('/preguntas', methods=['GET', 'POST'])
def preguntas():
    if 'user_id' not in session:
        return redirect(url_for('login'))

    if request.method == 'POST':
        intereses = ",".join(request.form.getlist('intereses'))
        objetivos = request.form['objetivos']
        experiencia = request.form['experiencia']

        nueva_respuesta = UsuarioRespuestas(
            user_id=session['user_id'],
            intereses=intereses,
            objetivos=objetivos,
            experiencia=experiencia
        )

        db.session.add(nueva_respuesta)
        db.session.commit()

        return redirect(url_for('dashboard'))

    return render_template('preguntas.html')


@app.route('/dashboard')
def dashboard():
    if 'user_id' not in session:
        return redirect(url_for('login'))

    usuario = session.get('usuario')
    respuestas = UsuarioRespuestas.query.filter_by(user_id=session['user_id']).first()
    videos = Video.query.filter_by(user_id=session['user_id']).all()

    return render_template("dashboard.html", usuario=usuario, respuestas=respuestas, videos=videos)


@app.route('/logout')
def logout():
    session.clear()
    flash("Sesión cerrada", "info")
    return redirect(url_for('home'))


# Dividir el texto en partes para generar imágenes y audios por fragmento
def dividir_en_frases(texto, max_long=200):
    return wrap(texto, width=max_long, break_long_words=False)


# Generar una imagen con DALL-E 3 por cada frase
def generar_imagen(prompt: str, nombre_archivo: str):
    response = client.images.generate(
        model="dall-e-3",
        prompt=prompt,
        size="1024x1024",
        quality="standard",
        n=1,
        response_format="b64_json"
    )
    image_data = response.data[0].b64_json
    image_bytes = base64.b64decode(image_data)

    os.makedirs("static/imagenes_generadas", exist_ok=True)
    ruta_salida = f"static/imagenes_generadas/{nombre_archivo}.png"
    with open(ruta_salida, "wb") as f:
        f.write(image_bytes)
    return ruta_salida


# Generar un guion dinámico adaptado al nivel y objetivos del usuario
def generar_guion_dinamico(respuestas):
    prompt = f"""
    Eres un profesor experto en crear cursos online. Genera un curso introductorio dividido en varias secciones (entre 2 y 7), adaptado al tema: "{respuestas.intereses}".
    El estudiante tiene nivel {respuestas.experiencia} y su objetivo es: "{respuestas.objetivos}".

    Escribe el contenido en español. Cada sección debe tener:
    - Un título que empiece por "Curso X:"
    - Un texto explicativo de entre 350 y 500 palabras, suficientemente largo para durar entre 3 y 4 minutos narrado.

    Formato:
    Curso 1: Título...
    Contenido...

    Curso 2: Título...
    Contenido...
    """

    respuesta = client.chat.completions.create(
        model="gpt-4",
        messages=[{"role": "user", "content": prompt}],
        temperature=0.7
    )
    return respuesta.choices[0].message.content


# Dividir el guion generado en secciones
def dividir_en_secciones(texto):
    secciones = re.split(r"(?=Curso \d+:)", texto)
    partes = []
    for seccion in secciones:
        if seccion.strip():
            lineas = seccion.strip().split("\n", 1)
            titulo = lineas[0].strip()
            contenido = lineas[1].strip() if len(lineas) > 1 else ""
            partes.append((titulo, contenido))
    return partes


# Generar el audio con ElevenLabs
def generar_audio_con_elevenlabs(texto, nombre_archivo):
    audio = elevenlabs.generate(
        text=texto,
        voice="en_us_male",  # Puedes probar diferentes voces como "en_us_female" o más opciones que ofrece ElevenLabs
        stability=0.75,  # Estabilidad de la voz, ajustable entre 0 y 1
        clarity=0.75,    # Claridad de la voz, ajustable entre 0 y 1
        speed=1.2        # Velocidad de la voz (1.0 es la velocidad normal)
    )
    
    ruta_audio = f"static/audios/{nombre_archivo}.mp3"
    
    with open(ruta_audio, 'wb') as f:
        f.write(audio)
    
    return ruta_audio


# Generar el curso completo, imágenes, audios y videos
def generar_curso_completo(respuestas, user_id):
    script_completo = generar_guion_dinamico(respuestas)
    secciones = dividir_en_secciones(script_completo)

    os.makedirs("static/audios", exist_ok=True)
    os.makedirs("static/videos", exist_ok=True)

    for idx, (titulo_seccion, texto) in enumerate(secciones, 1):
        nombre_base = f"curso_{user_id}_{idx}"

        # Imagen con DALL-E
        prompt_img = f"Ilustración educativa y moderna sobre: {titulo_seccion}. {texto[:150]}"
        ruta_img = generar_imagen(prompt_img, nombre_base)

        # Audio con ElevenLabs
        ruta_audio = generar_audio_con_elevenlabs(texto, nombre_base)

        # Video con ffmpeg
        ruta_video = f"videos/{nombre_base}.mp4"
        subprocess.run([
            "ffmpeg", "-y", "-loop", "1",
            "-i", ruta_img,
            "-i", ruta_audio,
            "-c:v", "libx264", "-tune", "stillimage",
            "-c:a", "aac", "-b:a", "192k",
            "-pix_fmt", "yuv420p", "-shortest",
            f"static/{ruta_video}"
        ])

        # Guardar en la base de datos
        video = Video(
            user_id=user_id,
            titulo=titulo_seccion,
            descripcion=texto[:200] + "...",
            script=texto,
            video_path=ruta_video
        )
        db.session.add(video)

    db.session.commit()
    return True


@app.route('/generar_curso')
def generar_curso():
    if 'user_id' not in session:
        return redirect(url_for('login'))

    respuestas = UsuarioRespuestas.query.filter_by(user_id=session['user_id']).first()
    if not respuestas:
        flash("Responde las preguntas primero", "warning")
        return redirect(url_for('preguntas'))

    generar_curso_completo(respuestas, session['user_id'])
    flash("✅ Curso generado con imágenes dinámicas", "success")
    return redirect(url_for('dashboard'))


if __name__ == '__main__':
    app.run(debug=True)
