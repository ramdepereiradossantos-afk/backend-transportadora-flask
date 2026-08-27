from datetime import datetime

from extensions import db


class LogAcao(db.Model):
    id = db.Column(db.Integer, primary_key=True)

    usuario_id = db.Column(
        db.Integer,
        db.ForeignKey("usuario_sistema.id"),
        nullable=True
    )

    usuario_nome = db.Column(
        db.String(120),
        nullable=True
    )

    perfil = db.Column(
        db.String(30),
        nullable=True
    )

    modulo = db.Column(
        db.String(80),
        nullable=True
    )

    acao = db.Column(
        db.String(120),
        nullable=False
    )

    entidade = db.Column(
        db.String(80),
        nullable=True
    )

    entidade_id = db.Column(
        db.Integer,
        nullable=True
    )

    detalhes = db.Column(
        db.Text,
        nullable=True
    )

    antes = db.Column(
        db.Text,
        nullable=True
    )

    depois = db.Column(
        db.Text,
        nullable=True
    )

    data_acao = db.Column(
        db.DateTime,
        default=datetime.utcnow
    )

    usuario = db.relationship(
        "UsuarioSistema",
        backref="logs"
    )
