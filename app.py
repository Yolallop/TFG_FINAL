from flask import Flask, render_template, request, redirect, url_for, flash, session
from flask_sqlalchemy import SQLAlchemy
import bcrypt
from urllib.parse import quote
from modelo import db, Usuario, UsuarioRespuestas, Video

app = Flask(__name__)
app.secret_key = 'clave_super_secreta'
app.config['SQLALCHEMY_DATABASE_URI'] = 'postgresql://postgres:postgres@localhost:5432/tfg_db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db.init_app(app)


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

    user_id = session['user_id']
    usuario = session['usuario']
    respuestas = UsuarioRespuestas.query.filter_by(user_id=user_id).first()
    videos = Video.query.filter_by(usuario_id=user_id).all()

    print("📹 Videos generados:", videos)  # 👈 Aquí lo estás imprimiendo en la terminal

    return render_template('dashboard.html', usuario=usuario, respuestas=respuestas, videos=videos)

def generar_script_curso(respuestas):
    if 'Programación' in respuestas.intereses:
        return "Curso básico de Python para principiantes."
    elif 'Marketing' in respuestas.intereses:
        return "Curso de marketing digital: aprende redes sociales y más."
    elif 'Diseño' in respuestas.intereses:
        return "Curso introductorio al diseño UX/UI."
    elif 'Negocios' in respuestas.intereses:
        return "Curso de emprendimiento y finanzas personales."
    else:
        return "Curso general para descubrir tus habilidades."


@app.route('/generar_curso')
def generar_curso():
    if 'user_id' not in session:
        return redirect(url_for('login'))

    respuestas = UsuarioRespuestas.query.filter_by(user_id=session['user_id']).first()
    if not respuestas:
        flash("Primero responde las preguntas", "warning")
        return redirect(url_for('preguntas'))

    script = generar_script_curso(respuestas)
    return redirect(url_for('crear_video_con_pictory', texto=quote(script)))


@app.route('/crear_video_con_pictory')
def crear_video_con_pictory():
    texto = request.args.get('texto')

    if not texto:
        return "Falta el texto para generar el video", 400

    job_id = generar_video_con_pictory_gpt(texto)

    if not job_id:
        flash("Hubo un problema generando tu video. Intenta más tarde.", "danger")
        return redirect(url_for('dashboard'))

    # Guardamos el job_id en la base de datos (simulamos URL por ahora)
    video_url_generado = f"https://pictory.ai/video/{job_id}"

    nuevo_video = Video(
        usuario_id=session['user_id'],
        titulo="Curso personalizado",
        url=video_url_generado
    )
    db.session.add(nuevo_video)
    db.session.commit()

    flash("Tu curso está en proceso de generación 🎬", "success")
    return redirect(url_for('dashboard'))


@app.route('/logout')
def logout():
    session.clear()
    flash("Sesión cerrada", "info")
    return redirect(url_for('home'))


if __name__ == '__main__':
    with app.app_context():
        from modelo import Video 
        print("🧱 Creando tablas en la base de datos...")

    app.run(debug=True)
