from datetime import datetime

from extensions import db


class Motorista(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    nome = db.Column(db.String(120), nullable=False)
    cpf = db.Column(db.String(20), nullable=True)
    cnh = db.Column(db.String(30), nullable=True)
    categoria_cnh = db.Column(db.String(5), nullable=True)
    validade_cnh = db.Column(db.String(20), nullable=True)
    telefone = db.Column(db.String(30), nullable=True)
    email = db.Column(db.String(120), nullable=True)
    usuario = db.Column(db.String(80), nullable=True, unique=True)
    senha = db.Column(db.String(120), nullable=True)

    # Status cadastral
    status = db.Column(
        db.String(20),
        default="Ativo"
    )

    # Status operacional
    disponibilidade = db.Column(
        db.String(20),
        default="Disponível"
    )

    observacoes = db.Column(db.Text, nullable=True)
    data_criacao = db.Column(
        db.DateTime,
        default=datetime.utcnow
    )


class Veiculo(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    placa = db.Column(db.String(20), nullable=False, unique=True)
    modelo = db.Column(db.String(100), nullable=True)
    marca = db.Column(db.String(80), nullable=True)
    tipo = db.Column(db.String(50), nullable=True)
    ano = db.Column(db.String(10), nullable=True)
    capacidade = db.Column(db.String(50), nullable=True)
    status = db.Column(db.String(20), default="Disponível")
    observacoes = db.Column(db.Text, nullable=True)
    data_criacao = db.Column(db.DateTime, default=datetime.utcnow)
