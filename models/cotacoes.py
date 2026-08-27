from datetime import datetime

from extensions import db


class Cotacao(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    cliente = db.Column(db.String(100), nullable=False)
    whatsapp = db.Column(db.String(20), nullable=False)
    origem = db.Column(db.String(100), nullable=False)
    destino = db.Column(db.String(100), nullable=False)
    tipo_carga = db.Column(db.String(50), nullable=False)
    observacoes = db.Column(db.Text, nullable=True)
    data_criacao = db.Column(db.DateTime, default=datetime.utcnow)
    status = db.Column(
    db.String(20),
    nullable=False,
    default="Pendente"
)

class Carga(db.Model):
    __tablename__ = "carga"

    id = db.Column(
        db.Integer,
        primary_key=True
    )

    cotacao_id = db.Column(
        db.Integer,
        db.ForeignKey("cotacao.id"),
        nullable=False,
        unique=True
    )

    cliente = db.Column(
        db.String(100),
        nullable=False
    )

    whatsapp = db.Column(
        db.String(20),
        nullable=False
    )

    origem = db.Column(
        db.String(100),
        nullable=False
    )

    destino = db.Column(
        db.String(100),
        nullable=False
    )

    tipo_carga = db.Column(
        db.String(50),
        nullable=False
    )

    observacoes = db.Column(
        db.Text,
        nullable=True
    )

    status = db.Column(
    db.String(30),
    nullable=False,
    default="Aguardando planejamento"
)
