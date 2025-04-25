from flask import Flask, render_template, request, redirect, url_for, flash, session
from pymongo import MongoClient
from config import OPENAI_API_KEY
import logging
from app_gtts_final import generar_video_completo
import os
import openai
import bcrypt

log = logging.getLogger('werkzeug')
log.setLevel(logging.DEBUG)

# Configuración de APIs
openai.api_key = OPENAI_API_KEY

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

@app.route('/dashboard')
def dashboard():
    if 'user_id' not in session:
        return redirect(url_for('login'))

    usuario = session['usuario']
    respuestas = prefs.find_one({"user_id": session['user_id']})
    videos = vids.find({"user_id": session['user_id']})

    return render_template('dashboard.html', usuario=usuario, respuestas=respuestas, videos=videos)
@app.route("/chatbot", methods=["POST", "GET"])
def chatbot():
    user_profile = {
        'name': session['name'],
        'last_name': session['last_name'],
        'status': session['status']
    }

    if request.method == 'POST':
        user_message = request.form["msg"]

        # Lógica para generar la respuesta del chatbot (usando OpenAI u otro servicio)
        response = openai.Completion.create(
            model="text-davinci-003",  # O el modelo que estés utilizando
            prompt=user_message,
            max_tokens=150
        )

        bot_response = response.choices[0].text.strip()

        # Devuelve la respuesta generada y la información del usuario
        return render_template('chatbot.html', bot_response=bot_response, user_profile=user_profile)
    else:
        # Si es GET, simplemente mostrar el chatbot sin respuesta
        return render_template('chatbot.html', user_profile=user_profile)


# Ruta para "Jarvis" si lo deseas como una página separada
@app.route("/jarvis")
def jarvis():
    user_profile = {
        'name': session['name'],
        'last_name': session['last_name'],
        'status': session['status']
    }
    return render_template('jarvis.html', user_profile=user_profile, longitud=num_notificaciones(), 
                           notificaciones=obtener_notificaciones(), tutor=isTutor())


# Ruta para la evaluación (si tienes alguna evaluación para los usuarios)
@app.route('/evaluacion')
def evaluacion():
    # Aquí iría el código para la evaluación (puedes agregarlo más adelante)
    return render_template('evaluacion.html')  # Asegúrate de crear la vista para la evaluación


@app.route('/generar_curso', methods=['POST'])
def generar_curso():
    if 'user_id' not in session:
        return redirect(url_for('login'))

    respuestas = prefs.find_one({"user_id": session['user_id']})
    if not respuestas:
        flash("Debes completar el formulario de preferencias primero.", "warning")
        return redirect(url_for('preguntas'))

    guion = generar_guion_dinamico(respuestas)
    ruta_video = generar_video_completo(guion)

    video = {
        "user_id": session['user_id'],
        "titulo": "Curso Personalizado",
        "descripcion": guion[:200],
        "script": guion,
        "video_path": ruta_video.replace("static/", "")
    }
    vids.insert_one(video)

    flash("Curso generado exitosamente 🎉", "success")
    return redirect(url_for('dashboard'))

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

# Ejecutar la app
if __name__ == '__main__':
    app.run(debug=True)
