from datetime import datetime

from extensions import db


class Rota(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    nome = db.Column(db.String(120), nullable=False)
    origem = db.Column(db.String(120), nullable=False)
    destino = db.Column(db.String(120), nullable=False)
    distancia = db.Column(db.String(50), nullable=True)
    previsao_tempo = db.Column(db.String(50), nullable=True)
    pedagio_estimado = db.Column(db.String(50), nullable=True)
    observacoes = db.Column(db.Text, nullable=True)
    status = db.Column(db.String(20), default="Ativa")
    data_criacao = db.Column(db.DateTime, default=datetime.utcnow)
