
from flask import Flask
from datetime import datetime
import os
import json
from config import (
    ALLOWED_EXTENSIONS,
    CLIENTE_TESTE_EMAIL,
    CLIENTE_TESTE_SENHA,
    CORS_ALLOW_HEADERS,
    CORS_METHODS,
    CORS_RESOURCES,
    DB_PATH as db_path,
    JWT_ACCESS_TOKEN_EXPIRES,
    JWT_SECRET_KEY,
    SENHA_ADMIN,
    SQLALCHEMY_DATABASE_URI,
    SQLALCHEMY_TRACK_MODIFICATIONS,
    UPLOAD_FOLDER as upload_folder,
    USUARIO_ADMIN
)
from extensions import cors, db, jwt
from utils.senhas import gerar_hash_senha

app = Flask(__name__)

app.config["JWT_SECRET_KEY"] = JWT_SECRET_KEY
app.config["JWT_ACCESS_TOKEN_EXPIRES"] = JWT_ACCESS_TOKEN_EXPIRES
app.config["UPLOAD_FOLDER"] = upload_folder
app.config["ALLOWED_EXTENSIONS"] = ALLOWED_EXTENSIONS
app.config["SQLALCHEMY_DATABASE_URI"] = SQLALCHEMY_DATABASE_URI
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = SQLALCHEMY_TRACK_MODIFICATIONS

os.makedirs(upload_folder, exist_ok=True)

db.init_app(app)
jwt.init_app(app)
cors.init_app(
    app,
    resources=CORS_RESOURCES,
    allow_headers=CORS_ALLOW_HEADERS,
    methods=CORS_METHODS
)

from models.usuarios import UsuarioSistema
from models.auditoria import LogAcao
from models.recursos import Motorista, Veiculo
from models.rotas import Rota

motorista_id = db.Column(
    db.Integer,
    db.ForeignKey("motorista.id"),
    nullable=True
)

motorista = db.relationship(
    "Motorista",
    backref="cargas"
)

data_criacao = db.Column(
    db.DateTime,
    default=datetime.utcnow
)
    
    

from models.operacao import Rastreamento, Viagem

from models.historicos import (
    HistoricoOperacao,
    HistoricoRastreamento,
    HistoricoViagem
)
from models.ocorrencias import OcorrenciaEntrega, OcorrenciaViagem
from models.comprovantes import ComprovanteEntrega, ArquivoComprovanteViagem
from models.localizacoes import LocalizacaoMotorista, LocalizacaoViagem
from services.compatibilidade_schema import (
    adicionar_colunas_auditoria,
    adicionar_colunas_operacionais
)
from routes.public import public_bp
from routes.auth import auth_bp
from routes.admin_clientes import admin_clientes_bp
from routes.admin_veiculos import admin_veiculos_bp
from routes.admin_motoristas import admin_motoristas_bp
from routes.admin_usuarios import admin_usuarios_bp
from routes.admin_dashboard import admin_dashboard_bp
from routes.admin_relatorios import admin_relatorios_bp
from routes.admin_cotacoes import admin_cotacoes_bp
from routes.portal_cliente import portal_cliente_bp
from routes.portal_motorista import portal_motorista_bp
from routes.admin_cargas import admin_cargas_bp
from routes.admin_viagens import admin_viagens_bp

app.register_blueprint(public_bp)
app.register_blueprint(auth_bp)
app.register_blueprint(admin_clientes_bp)
app.register_blueprint(admin_veiculos_bp)
app.register_blueprint(admin_motoristas_bp)
app.register_blueprint(admin_usuarios_bp)
app.register_blueprint(admin_dashboard_bp)
app.register_blueprint(admin_relatorios_bp)
app.register_blueprint(admin_cotacoes_bp)
app.register_blueprint(portal_cliente_bp)
app.register_blueprint(portal_motorista_bp)
app.register_blueprint(admin_cargas_bp)
app.register_blueprint(admin_viagens_bp)

with app.app_context():
    db.create_all()

    adicionar_colunas_operacionais()
    adicionar_colunas_auditoria()

    admin_padrao = UsuarioSistema.query.filter_by(
        usuario="admin"
    ).first()

    if not admin_padrao:
        admin_padrao = UsuarioSistema(
            nome="Administrador",
            usuario="admin",
            senha=gerar_hash_senha("ramos123"),
            perfil="administrador",
            ativo=True
        )

        db.session.add(admin_padrao)
        db.session.commit()










    
        
    


    

    














        
    
    
    
    

    
        

    
    
if __name__ == "__main__":
    app.run(debug=True)
