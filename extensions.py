import sqlite3

from flask_cors import CORS
from flask_jwt_extended import JWTManager
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import event
from sqlalchemy.engine import Engine


@event.listens_for(Engine, "connect")
def ativar_foreign_keys_sqlite(conexao_dbapi, _registro_conexao):
    if not isinstance(conexao_dbapi, sqlite3.Connection):
        return

    cursor = conexao_dbapi.cursor()
    cursor.execute("PRAGMA foreign_keys = ON")
    cursor.close()


db = SQLAlchemy()
jwt = JWTManager()
cors = CORS()
