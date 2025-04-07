# modelo.py
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime

db = SQLAlchemy()

class Usuario(db.Model):
    __tablename__ = 'usuarios'
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    nombre = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(100), unique=True, nullable=False)
    password = db.Column(db.String(255), nullable=False)
    respuestas = db.relationship('UsuarioRespuestas', backref='usuario', lazy=True)
    videos = db.relationship('Video', backref='usuario', lazy=True)

class UsuarioRespuestas(db.Model):
    __tablename__ = 'usuarios_respuestas'
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    user_id = db.Column(db.Integer, db.ForeignKey('usuarios.id'), nullable=False)
    intereses = db.Column(db.Text)
    objetivos = db.Column(db.Text)
    experiencia = db.Column(db.String(50))


class Video(db.Model):
    __tablename__ = 'videos'
    id = db.Column(db.Integer, primary_key=True)
    usuario_id = db.Column(db.Integer, db.ForeignKey('usuarios.id'), nullable=False)
    titulo = db.Column(db.String(255))
    url = db.Column(db.String(500))  # Enlace del video generado
    fecha_creacion = db.Column(db.DateTime, default=datetime.utcnow)

    