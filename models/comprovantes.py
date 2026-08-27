from datetime import datetime

from extensions import db


class ComprovanteEntrega(db.Model):
    
    __tablename__ = "finalizacao_entrega"
    
    id = db.Column(
        db.Integer,
        primary_key=True
    )

    viagem_id = db.Column(
        db.Integer,
        db.ForeignKey("viagem.id"),
        nullable=False
    )

    recebedor = db.Column(
        db.String(120),
        nullable=False
    )

    observacao = db.Column(
        db.Text
    )

    data_entrega = db.Column(
        db.DateTime,
        default=datetime.utcnow
    )

    viagem = db.relationship(
        "Viagem",
        backref="comprovantes"
    )  


class ArquivoComprovanteViagem(db.Model):
    id = db.Column(db.Integer, primary_key=True)

    viagem_id = db.Column(
        db.Integer,
        db.ForeignKey("viagem.id"),
        nullable=False
    )

    nome_arquivo = db.Column(db.String(255), nullable=False)

    data_upload = db.Column(
        db.DateTime,
        default=datetime.utcnow
    )

    viagem = db.relationship(
        "Viagem",
        backref="arquivos_comprovante"
    )
