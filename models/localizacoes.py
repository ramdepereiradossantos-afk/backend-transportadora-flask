from datetime import datetime

from extensions import db


class LocalizacaoMotorista(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    motorista_id = db.Column(db.Integer, db.ForeignKey('motorista.id'))
    rastreamento_id = db.Column(db.Integer, db.ForeignKey('rastreamento.id'))

    latitude = db.Column(db.String(50))
    longitude = db.Column(db.String(50))

    data_registro = db.Column(db.DateTime, default=datetime.utcnow)

    motorista = db.relationship('Motorista')
    rastreamento = db.relationship('Rastreamento')


class LocalizacaoViagem(db.Model):
    id = db.Column(db.Integer, primary_key=True)

    viagem_id = db.Column(
        db.Integer,
        db.ForeignKey("viagem.id"),
        nullable=False
    )

    localizacao = db.Column(
        db.String(180),
        nullable=False
    )

    observacao = db.Column(
        db.Text
    )

    data_registro = db.Column(
        db.DateTime,
        default=datetime.utcnow
    )

    viagem = db.relationship(
        "Viagem",
        backref="localizacoes"
    )
