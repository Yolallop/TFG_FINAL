from flask import Flask, render_template, request, redirect, url_for, flash, session
from flask_sqlalchemy import SQLAlchemy
from config import EDEN_API_KEY
from modelo import db, Usuario, UsuarioRespuestas, Video
from flask_bcrypt import Bcrypt
import os, re, uuid, time, requests, subprocess
import base64
# Config Flask
app = Flask(__name__)
app.secret_key = 'clave_super_secreta'
app.config['SQLALCHEMY_DATABASE_URI'] = 'postgresql://postgres:postgres@localhost:5432/tfg_db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
bcrypt = Bcrypt(app)
db.init_app(app)

# ------------------- FUNCIONES IA CON EDEN -------------------

def generar_guion_con_eden_ai(respuestas):
    prompt = f"""
    Eres un experto en formación online. Crea un curso dividido en secciones (entre 2 y 7), adaptado al tema: "{respuestas.intereses}".
    Nivel del alumno: {respuestas.experiencia}. Objetivo: {respuestas.objetivos}.

    Escribe en español. Cada sección debe tener:
    - Título que comience por "Curso X:"
    - Explicación de 350 a 500 palabras

    Ejemplo:
    Curso 1: Introducción...
    Contenido...

    Curso 2: ...
    """
    headers = {
        "Authorization": f"Bearer {EDEN_API_KEY}",
        "Content-Type": "application/json"
    }

    data = {
        "providers": "openai",
        "text": prompt,
        "temperature": 0.6,
        "max_tokens": 1500,
        "fallback_providers": "cohere"
    }

    response = requests.post("https://api.edenai.run/v2/text/generation", headers=headers, json=data)

    if response.status_code == 200:
        resultado = response.json()
        print("🧠 Respuesta generación:", resultado)

        # ✅ Intenta obtener el texto generado, sea cual sea el proveedor
        for proveedor in resultado:
            if 'generated_text' in resultado[proveedor]:
                return resultado[proveedor]['generated_text']
        
        print("⚠️ No se encontró 'generated_text' en ningún proveedor.")
        return ""
    
    else:
        print("❌ Error al generar guion:", response.text)
        return ""

def traducir_al_ingles(texto):
    headers = {
        "Authorization": f"Bearer {EDEN_API_KEY}",
        "Content-Type": "application/json"
    }
    data = {
        "providers": "google",
        "source_language": "es",
        "target_language": "en",
        "text": texto
    }

    response = requests.post("https://api.edenai.run/v2/translation/automatic_translation",
                             headers=headers, json=data)

    if response.status_code == 200:
        respuesta = response.json()
        print("🔁 Traducción:", respuesta)
        if 'google' in respuesta:
            # Usar 'text' si no hay 'translated_text'
            return respuesta['google'].get('translated_text') or respuesta['google'].get('text') or texto
        else:
            print("⚠️ No se encontró texto traducido.")
            return texto
    else:
        print("❌ Error al traducir:", response.text)
        return texto
import base64

def generar_imagen_con_eden(texto):
    headers = {
        "Authorization": f"Bearer {EDEN_API_KEY}",
        "Content-Type": "application/json"
    }

    texto_en = traducir_al_ingles(texto)

    data = {
        "providers": "stabilityai",
        "text": texto_en,
        "resolution": "512x512"
    }

    response = requests.post("https://api.edenai.run/v2/image/generation", headers=headers, json=data)

    if response.status_code == 200:
        resultado = response.json()
        print("🖼️ Respuesta Eden:", resultado)

        imagen_data = resultado['stabilityai'].get('items', [{}])[0].get('image')

        if imagen_data.startswith("http"):
            # Es una URL normal
            img_data = requests.get(imagen_data).content
        else:
            # Es base64, decodificar
            img_data = base64.b64decode(imagen_data)

        nombre = f"static/imagenes_generadas/{uuid.uuid4()}.png"
        with open(nombre, 'wb') as f:
            f.write(img_data)

        return nombre
    else:
        print("❌ Error al generar imagen:", response.text)
        return None



def generar_audio_con_eden(texto):
    headers = {
        "Authorization": f"Bearer {EDEN_API_KEY}",
        "Content-Type": "application/json"
    }
    data = {
        "providers": "google",
        "language": "es-ES",
        "text": texto,
        "option": "FEMALE",
        "voice_type": "neural"
    }
    response = requests.post("https://api.edenai.run/v2/audio/text_to_speech", headers=headers, json=data)
    if response.status_code == 200:
        url_audio = response.json()['google']['audio_resource_url']
        audio = requests.get(url_audio).content
        nombre = f"static/audios/{uuid.uuid4()}.mp3"
        with open(nombre, 'wb') as f:
            f.write(audio)
        return nombre
    else:
        print("❌ Error al generar audio:", response.text)
        return None

def crear_video(imagen, audio, nombre_base):
    salida = f"static/videos/{nombre_base}.mp4"
    comando = [
        "ffmpeg", "-y", "-loop", "1", "-i", imagen, "-i", audio,
        "-c:v", "libx264", "-tune", "stillimage", "-c:a", "aac", "-b:a", "192k",
        "-shortest", salida
    ]
    subprocess.run(comando, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    return salida

# ---------------- RUTAS ----------------
@app.route('/')
def home():
    return render_template('index.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        nombre = request.form['nombre']
        email = request.form['email']
        password = request.form['password']

        if Usuario.query.filter_by(email=email).first():
            flash('El correo ya está registrado.', 'danger')
            return redirect(url_for('register'))

        hashed = bcrypt.generate_password_hash(password).decode('utf-8')
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
        if usuario and bcrypt.check_password_hash(usuario.password, password):
            session['user_id'] = usuario.id
            session['usuario'] = usuario.nombre
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

@app.route('/generar_curso')
def generar_curso():
    if 'user_id' not in session:
        return redirect(url_for('login'))

    respuestas = UsuarioRespuestas.query.filter_by(user_id=session['user_id']).first()
    if not respuestas:
        flash("Responde las preguntas primero", "warning")
        return redirect(url_for('preguntas'))

    guion = generar_guion_con_eden_ai(respuestas)
    secciones = re.split(r"(?=Curso \d+:)", guion)

    for idx, seccion in enumerate(secciones):
        if seccion.strip():
            titulo = seccion.strip().split('\n')[0].strip()
            contenido = '\n'.join(seccion.strip().split('\n')[1:]).strip()
            imagen = generar_imagen_con_eden(titulo + ". " + contenido[:150])
            audio = generar_audio_con_eden(contenido)
            if imagen and audio:
                nombre_base = f"curso_{session['user_id']}_{idx+1}"
                ruta_video = crear_video(imagen, audio, nombre_base)
                nuevo = Video(
                    user_id=session['user_id'],
                    titulo=titulo,
                    descripcion=contenido[:200],
                    script=contenido,
                    video_path=ruta_video
                )
                db.session.add(nuevo)
                db.session.commit()
            time.sleep(3)

    flash("✅ Curso generado con videos profesionales (Eden AI)", "success")
    return redirect(url_for('dashboard'))

@app.route('/evaluacion')
def evaluacion():
    return render_template('evaluacion.html')

if __name__ == '__main__':
    app.run(debug=True)
