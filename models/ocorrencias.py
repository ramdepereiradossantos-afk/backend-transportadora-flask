from datetime import datetime

from extensions import db


class OcorrenciaEntrega(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    rastreamento_id = db.Column(db.Integer, db.ForeignKey('rastreamento.id'), nullable=False)
    titulo = db.Column(db.String(100), nullable=False)
    descricao = db.Column(db.Text, nullable=False)
    data_ocorrencia = db.Column(db.DateTime, default=datetime.utcnow)

    rastreamento = db.relationship('Rastreamento', backref='ocorrencias')


class OcorrenciaViagem(db.Model):
    id = db.Column(db.Integer, primary_key=True)

    viagem_id = db.Column(
        db.Integer,
        db.ForeignKey("viagem.id"),
        nullable=False
    )

    descricao = db.Column(
        db.Text,
        nullable=False
    )

    data_criacao = db.Column(
        db.DateTime,
        default=datetime.utcnow
    )

    viagem = db.relationship(
        "Viagem",
        backref="ocorrencias"
    )
