from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()

class Usuario(db.Model):
    __tablename__ = 'usuarios'
    id = db.Column(db.Integer, primary_key=True)
    nombre = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password = db.Column(db.String(200), nullable=False)

class UsuarioRespuestas(db.Model):
    __tablename__ = 'respuestas'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('usuarios.id'))
    intereses = db.Column(db.String(200))
    objetivos = db.Column(db.Text)
    experiencia = db.Column(db.String(50))

class Video(db.Model):
    __tablename__ = 'videos'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('usuarios.id'))
    titulo = db.Column(db.String(200))
    descripcion = db.Column(db.Text)
    script = db.Column(db.Text)
    video_path = db.Column(db.String(300))
