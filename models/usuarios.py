from datetime import datetime

from extensions import db


class UsuarioSistema(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    nome = db.Column(db.String(120), nullable=False)
    usuario = db.Column(db.String(80), nullable=False, unique=True)
    email = db.Column(db.String(120), nullable=True, default="")
    senha = db.Column(db.String(120), nullable=False)
    perfil = db.Column(db.String(30), nullable=False, default="operador")
    ativo = db.Column(db.Boolean, default=True)
    data_criacao = db.Column(db.DateTime, default=datetime.utcnow)
