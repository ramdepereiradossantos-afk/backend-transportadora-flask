from datetime import datetime

from extensions import db


class ClienteUsuario(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    cliente_id = db.Column(db.Integer, db.ForeignKey('cliente.id'), nullable=True)
    cliente_relacao = db.relationship('Cliente', backref='usuarios_acesso')

    nome = db.Column(db.String(100), nullable=False)
    empresa = db.Column(db.String(100), nullable=False, unique=True)
    email = db.Column(db.String(120), nullable=False, unique=True)
    senha = db.Column(db.String(120), nullable=False)
    ativo = db.Column(db.Boolean, default=True)
    data_criacao = db.Column(db.DateTime, default=datetime.utcnow)


class Cliente(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    razao_social = db.Column(db.String(150), nullable=False)
    nome_fantasia = db.Column(db.String(150), nullable=True)
    documento = db.Column(db.String(30), nullable=True)
    responsavel = db.Column(db.String(100), nullable=True)
    email = db.Column(db.String(120), nullable=True)
    telefone = db.Column(db.String(30), nullable=True)
    endereco = db.Column(db.String(200), nullable=True)
    cidade = db.Column(db.String(100), nullable=True)
    estado = db.Column(db.String(2), nullable=True)
    ativo = db.Column(db.Boolean, default=True)
    data_criacao = db.Column(db.DateTime, default=datetime.utcnow)
