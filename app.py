from flask import Flask, render_template, request, redirect, url_for, flash, session
from flask_sqlalchemy import SQLAlchemy
from flask_cors import CORS
from datetime import datetime, timedelta
from functools import wraps
from werkzeug.utils import secure_filename
import os

app = Flask(__name__)
CORS(app, resources={
    r"/api/*": {
        "origins": [
            "http://localhost:5173",
            "http://127.0.0.1:5173",
            "http://localhost:5174",
            "http://127.0.0.1:5174"
        ]
    }
})
app.secret_key = os.environ.get(
    "SECRET_KEY",
    "ramos_transportes_chave_super_segura_2026_abc123"
)

USUARIO_ADMIN = os.environ.get("USUARIO_ADMIN", "admin")
SENHA_ADMIN = os.environ.get("SENHA_ADMIN", "ramos123")

CLIENTE_TESTE_EMAIL = os.environ.get("CLIENTE_TESTE_EMAIL", "cliente@infinity.com")
CLIENTE_TESTE_SENHA = os.environ.get("CLIENTE_TESTE_SENHA", "123456")

base_dir = os.path.abspath(os.path.dirname(__file__))
db_path = os.path.join(base_dir, "database.db")

upload_folder = os.path.join(base_dir, "static", "uploads")
os.makedirs(upload_folder, exist_ok=True)

app.config["UPLOAD_FOLDER"] = upload_folder
app.config["ALLOWED_EXTENSIONS"] = {"png", "jpg", "jpeg", "pdf"}

app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///" + db_path
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

db = SQLAlchemy(app)

def login_obrigatorio(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not session.get("admin_logado"):
            flash("Você precisa estar logado para acessar essa área.", "erro")
            return redirect(url_for("login", next=request.path))
        return f(*args, **kwargs)
    return decorated_function

def cliente_login_obrigatorio(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not session.get("cliente_logado"):
            flash("Você precisa estar logado como cliente para acessar essa área.", "erro")
            return redirect(url_for("cliente_login"))
        return f(*args, **kwargs)
    return decorated_function

def arquivo_permitido(nome_arquivo):
    return "." in nome_arquivo and nome_arquivo.rsplit(".", 1)[1].lower() in app.config["ALLOWED_EXTENSIONS"]
def motorista_login_obrigatorio(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not session.get("motorista_logado"):
            flash("Você precisa estar logado como motorista.", "erro")
            return redirect(url_for("motorista_login"))
        return f(*args, **kwargs)
    return decorated_function

class Cotacao(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    cliente = db.Column(db.String(100), nullable=False)
    whatsapp = db.Column(db.String(20), nullable=False)
    origem = db.Column(db.String(100), nullable=False)
    destino = db.Column(db.String(100), nullable=False)
    tipo_carga = db.Column(db.String(50), nullable=False)
    observacoes = db.Column(db.Text, nullable=True)
    data_criacao = db.Column(db.DateTime, default=datetime.utcnow)

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

class UsuarioSistema(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    nome = db.Column(db.String(120), nullable=False)
    usuario = db.Column(db.String(80), nullable=False, unique=True)
    senha = db.Column(db.String(120), nullable=False)
    perfil = db.Column(db.String(30), nullable=False, default="operador")
    ativo = db.Column(db.Boolean, default=True)
    data_criacao = db.Column(db.DateTime, default=datetime.utcnow)

class LogAcao(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    usuario_id = db.Column(db.Integer, db.ForeignKey('usuario_sistema.id'), nullable=True)
    usuario_nome = db.Column(db.String(120), nullable=True)
    acao = db.Column(db.String(120), nullable=False)
    detalhes = db.Column(db.Text, nullable=True)
    data_acao = db.Column(db.DateTime, default=datetime.utcnow)

    usuario = db.relationship('UsuarioSistema', backref='logs')

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
    status = db.Column(db.String(20), default="Ativo")
    observacoes = db.Column(db.Text, nullable=True)
    data_criacao = db.Column(db.DateTime, default=datetime.utcnow)

class LocalizacaoMotorista(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    motorista_id = db.Column(db.Integer, db.ForeignKey('motorista.id'))
    rastreamento_id = db.Column(db.Integer, db.ForeignKey('rastreamento.id'))

    latitude = db.Column(db.String(50))
    longitude = db.Column(db.String(50))

    data_registro = db.Column(db.DateTime, default=datetime.utcnow)

    motorista = db.relationship('Motorista')
    rastreamento = db.relationship('Rastreamento')

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
    

class Rastreamento(db.Model):
    id = db.Column(db.Integer, primary_key=True)

    rota_id = db.Column(db.Integer, db.ForeignKey('rota.id'), nullable=True)
    rota_relacao = db.relationship('Rota', backref='rastreamentos')

    cliente_id = db.Column(db.Integer, db.ForeignKey('cliente.id'), nullable=True)
    cliente_relacao = db.relationship('Cliente', backref='rastreamentos')

    motorista_id = db.Column(db.Integer, db.ForeignKey('motorista.id'), nullable=True)
    motorista_relacao = db.relationship('Motorista', backref='rastreamentos')

    veiculo_id = db.Column(db.Integer, db.ForeignKey('veiculo.id'), nullable=True)
    veiculo_relacao = db.relationship('Veiculo', backref='rastreamentos')
  
    destino_latitude = db.Column(db.String(50), nullable=True)
    destino_longitude = db.Column(db.String(50), nullable=True)

    codigo = db.Column(db.String(30), unique=True, nullable=False)
    cliente = db.Column(db.String(100), nullable=False)  # vamos manter por compatibilidade
    status = db.Column(db.String(50), nullable=False)
    local_atual = db.Column(db.String(100), nullable=False)
    destino = db.Column(db.String(100), nullable=False)
    previsao_entrega = db.Column(db.DateTime, nullable=True)
    ultima_atualizacao = db.Column(db.DateTime, default=datetime.utcnow)


class HistoricoRastreamento(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    rastreamento_id = db.Column(db.Integer, db.ForeignKey('rastreamento.id'), nullable=False)
    status = db.Column(db.String(50), nullable=False)
    local = db.Column(db.String(100), nullable=False)
    observacao = db.Column(db.Text)
    data_evento = db.Column(db.DateTime, default=datetime.utcnow)

    rastreamento = db.relationship('Rastreamento', backref='historico')


class ComprovanteEntrega(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    rastreamento_id = db.Column(db.Integer, db.ForeignKey('rastreamento.id'), nullable=False)
    nome_arquivo = db.Column(db.String(255), nullable=False)
    observacao = db.Column(db.Text)
    data_upload = db.Column(db.DateTime, default=datetime.utcnow)

    rastreamento = db.relationship('Rastreamento', backref='comprovantes')


class OcorrenciaEntrega(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    rastreamento_id = db.Column(db.Integer, db.ForeignKey('rastreamento.id'), nullable=False)
    titulo = db.Column(db.String(100), nullable=False)
    descricao = db.Column(db.Text, nullable=False)
    data_ocorrencia = db.Column(db.DateTime, default=datetime.utcnow)

    rastreamento = db.relationship('Rastreamento', backref='ocorrencias')


@app.route("/")
def index():
    return {
        "mensagem": "Backend da Transportadora Ramos ativo.",
        "status": "online"
    }

@app.route("/sobre")
def sobre():
    return render_template("sobre.html")


@app.route("/parceiros")
def parceiros():
    return render_template("parceiros.html")

@app.route("/servicos")
def servicos():
    return render_template("servicos.html")


@app.route("/areas-atendidas")
def areas_atendidas():
    return render_template("areas_atendidas.html")


@app.route("/contato")
def contato():
    return render_template("contato.html")

@app.route("/cliente/login", methods=["GET", "POST"])
def cliente_login():
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        senha = request.form.get("senha", "").strip()

        cliente = ClienteUsuario.query.filter_by(email=email, senha=senha, ativo=True).first()

        if not cliente:
            flash("E-mail ou senha inválidos.", "erro")
            return redirect(url_for("cliente_login"))

        # 🔥 LOGIN
        session["cliente_logado"] = True
        session["cliente_id"] = cliente.id
        session["cliente_nome"] = cliente.nome
        session["cliente_empresa"] = cliente.empresa

        # 🔥 NOVO (IMPORTANTÍSSIMO)
        session["cliente_id_ref"] = cliente.cliente_id

        flash("Login realizado com sucesso!", "sucesso")
        return redirect(url_for("cliente_painel"))

    return render_template("cliente_login.html")

@app.route("/cliente/painel")
@cliente_login_obrigatorio
def cliente_painel():
    cliente_id_ref = session.get("cliente_id_ref")
    empresa = session.get("cliente_empresa")

    if cliente_id_ref:
        cargas = Rastreamento.query.filter_by(cliente_id=cliente_id_ref).order_by(
            Rastreamento.ultima_atualizacao.desc()
        ).all()
    else:
        cargas = Rastreamento.query.filter_by(cliente=empresa).order_by(
            Rastreamento.ultima_atualizacao.desc()
        ).all()

    total_cargas = len(cargas)
    entregues = len([c for c in cargas if c.status == "Entregue"])
    em_transito = len([c for c in cargas if c.status == "Em trânsito"])
    em_coleta = len([c for c in cargas if c.status == "Em coleta"])
    saiu_entrega = len([c for c in cargas if c.status == "Saiu para entrega"])

    return render_template(
        "cliente_painel.html",
        cargas=cargas,
        total_cargas=total_cargas,
        entregues=entregues,
        em_transito=em_transito,
        em_coleta=em_coleta,
        saiu_entrega=saiu_entrega
    )


@app.route("/cliente/carga/<int:id>")
@cliente_login_obrigatorio
def cliente_carga_detalhe(id):
    carga = Rastreamento.query.get_or_404(id)

    cliente_id_ref = session.get("cliente_id_ref")
    empresa = session.get("cliente_empresa")

    if cliente_id_ref:
        if carga.cliente_id != cliente_id_ref:
            flash("Acesso não autorizado.", "erro")
            return redirect(url_for("cliente_painel"))
    else:
        if carga.cliente != empresa:
            flash("Acesso não autorizado.", "erro")
            return redirect(url_for("cliente_painel"))

    historico = HistoricoRastreamento.query.filter_by(
        rastreamento_id=id
    ).order_by(HistoricoRastreamento.data_evento.desc()).all()

    comprovantes = ComprovanteEntrega.query.filter_by(
        rastreamento_id=id
    ).order_by(ComprovanteEntrega.data_upload.desc()).all()

    ocorrencias = OcorrenciaEntrega.query.filter_by(
        rastreamento_id=id
    ).order_by(OcorrenciaEntrega.data_ocorrencia.desc()).all()

    distancia_restante, eta_estimado = calcular_eta(carga)

    return render_template(
        "cliente_carga_detalhe.html",
        carga=carga,
        historico=historico,
        comprovantes=comprovantes,
        ocorrencias=ocorrencias,
        now=datetime.utcnow(),
        distancia_restante=distancia_restante,
        eta_estimado=eta_estimado
) 

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        usuario_digitado = request.form.get("usuario", "").strip()
        senha_digitada = request.form.get("senha", "").strip()

        usuario = UsuarioSistema.query.filter_by(
            usuario=usuario_digitado,
            senha=senha_digitada,
            ativo=True
        ).first()

        if usuario:
            session["admin_logado"] = True
            session["usuario_sistema_id"] = usuario.id
            session["usuario_sistema_nome"] = usuario.nome
            session["usuario_sistema_perfil"] = usuario.perfil

            registrar_log("Login no sistema", f"Usuário {usuario.nome} acessou o painel.")

            flash("Login realizado com sucesso!", "sucesso")

            next_page = request.args.get("next")
            return redirect(next_page or url_for("admin"))

        flash("Usuário ou senha incorretos.", "erro")

    return render_template("login.html")


@app.route("/logout")
def logout():
    if session.get("usuario_sistema_nome"):
        registrar_log("Logout do sistema", f"Usuário {session.get('usuario_sistema_nome')} saiu do painel.")

    session.pop("admin_logado", None)
    session.pop("usuario_sistema_id", None)
    session.pop("usuario_sistema_nome", None)
    session.pop("usuario_sistema_perfil", None)

    flash("Você saiu do painel.", "sucesso")
    return redirect(url_for("login"))


@app.route("/enviar_cotacao", methods=["POST"])
def enviar_cotacao():
    cliente = request.form.get("cliente", "").strip()
    whatsapp = request.form.get("whatsapp", "").strip()
    origem = request.form.get("origem", "").strip()
    destino = request.form.get("destino", "").strip()
    tipo_carga = request.form.get("tipo_carga", "").strip()
    observacoes = request.form.get("observacoes", "").strip()

    if not all([cliente, whatsapp, origem, destino, tipo_carga]):
        flash("Preencha todos os campos obrigatórios da cotação.", "erro")
        return redirect(url_for("index") + "#cotacao")

    nova_cotacao = Cotacao(
        cliente=cliente,
        whatsapp=whatsapp,
        origem=origem,
        destino=destino,
        tipo_carga=tipo_carga,
        observacoes=observacoes
    )
    db.session.add(nova_cotacao)
    db.session.commit()

    flash("Orçamento enviado com sucesso!", "sucesso")
    return redirect(url_for("index") + "#cotacao")


@app.route("/rastreamento", methods=["POST"])
def rastreamento():
    codigo = request.form.get("codigo", "").strip().upper()

    if not codigo:
        flash("Digite um código para consultar.", "erro")
        return redirect(url_for("index") + "#rastreamento")

    carga = Rastreamento.query.filter_by(codigo=codigo).first()

    if not carga:
        flash("Código de rastreamento não encontrado.", "erro")
        return redirect(url_for("index") + "#rastreamento")

    return render_template("rastreamento_resultado.html", carga=carga)

@app.route("/admin/rastreamentos")
@login_obrigatorio
def admin_rastreamento():
    cargas = Rastreamento.query.order_by(Rastreamento.ultima_atualizacao.desc()).all()
    agora = datetime.utcnow()
    grafico_status_labels=["Em coleta", "Em trânsito", "Saiu para entrega", "Entregue", "Atrasadas"],
    return render_template("admin_rastreamento.html", cargas=cargas, agora=agora)

@app.route("/admin")
@login_obrigatorio
def admin():
    total_cargas = Rastreamento.query.count()

    em_coleta = Rastreamento.query.filter_by(status="Em coleta").count()
    em_transito = Rastreamento.query.filter_by(status="Em trânsito").count()
    saiu_entrega = Rastreamento.query.filter_by(status="Saiu para entrega").count()
    entregues = Rastreamento.query.filter_by(status="Entregue").count()

    total_ocorrencias = OcorrenciaEntrega.query.count()

    agora = datetime.utcnow()

    atrasadas = Rastreamento.query.filter(
        Rastreamento.previsao_entrega != None,
        Rastreamento.previsao_entrega < agora,
        Rastreamento.status != "Entregue"
    ).count()

    cotacoes = Cotacao.query.order_by(Cotacao.data_criacao.desc()).all()

    return render_template(
        "admin.html",
        cotacoes=cotacoes,
        total_cargas=total_cargas,
        em_coleta=em_coleta,
        em_transito=em_transito,
        saiu_entrega=saiu_entrega,
        entregues=entregues,
        total_ocorrencias=total_ocorrencias,
        atrasadas=atrasadas,
        grafico_status_labels=[
            "Em coleta",
            "Em trânsito",
            "Saiu para entrega",
            "Entregue",
            "Atrasadas"
        ],
        grafico_status_valores=[
            em_coleta,
            em_transito,
            saiu_entrega,
            entregues,
            atrasadas
        ]
    )
@app.route("/admin/rastreamentos/editar/<int:id>", methods=["GET", "POST"])
@login_obrigatorio
def editar_rastreamento(id):
    carga = Rastreamento.query.get_or_404(id)

    clientes = Cliente.query.filter_by(ativo=True).order_by(Cliente.razao_social.asc()).all()
    motoristas = Motorista.query.filter_by(status="Ativo").order_by(Motorista.nome.asc()).all()
    veiculos = Veiculo.query.order_by(Veiculo.placa.asc()).all()
    rotas = Rota.query.filter_by(status="Ativa").order_by(Rota.nome.asc()).all()

    if request.method == "POST":
        novo_codigo = request.form.get("codigo", "").strip().upper()
        cliente_id = request.form.get("cliente_id", "").strip()
        motorista_id = request.form.get("motorista_id", "").strip()
        veiculo_id = request.form.get("veiculo_id", "").strip()
        rota_id = request.form.get("rota_id", "").strip()
        carga.destino_latitude = request.form.get("destino_latitude", "").strip()
        carga.destino_longitude = request.form.get("destino_longitude", "").strip()
        carga.destino = request.form.get("destino", "").strip()

        duplicado = Rastreamento.query.filter(
            Rastreamento.codigo == novo_codigo,
            Rastreamento.id != carga.id
        ).first()

        if duplicado:
            flash("Já existe outro rastreamento com esse código.", "erro")
            return redirect(url_for("editar_rastreamento", id=id))

        cliente_obj = Cliente.query.get(cliente_id)

        if not cliente_obj:
            flash("Cliente não encontrado.", "erro")
            return redirect(url_for("editar_rastreamento", id=id))

        carga.codigo = novo_codigo
        carga.cliente_id = cliente_obj.id
        carga.cliente = cliente_obj.razao_social
        carga.motorista_id = int(motorista_id) if motorista_id else None
        carga.veiculo_id = int(veiculo_id) if veiculo_id else None
        carga.rota_id = int(rota_id) if rota_id else None
        carga.status = request.form.get("status", "").strip()
        carga.local_atual = request.form.get("local_atual", "").strip()
        carga.destino = request.form.get("destino", "").strip()
        carga.ultima_atualizacao = datetime.utcnow()

        db.session.commit()

        historico = HistoricoRastreamento(
            rastreamento_id=carga.id,
            status=carga.status,
            local=carga.local_atual,
            observacao="Atualização manual no painel"
        )

        db.session.add(historico)
        db.session.commit()

        registrar_log(
    "Edição de rastreamento",
    f"Carga {carga.codigo} atualizada. Status: {carga.status}."
)

        flash("Rastreamento atualizado com sucesso!", "sucesso")
        return redirect(url_for("admin_rastreamento"))

    return render_template(
        "editar_rastreamento.html",
        carga=carga,
        clientes=clientes,
        motoristas=motoristas,
        veiculos=veiculos,
        rotas=rotas,
    )

@app.route("/admin/rastreamentos/<int:id>/comprovante", methods=["GET", "POST"])
@login_obrigatorio
def upload_comprovante(id):
    carga = Rastreamento.query.get_or_404(id)

    if request.method == "POST":
        arquivo = request.files.get("arquivo")
        observacao = request.form.get("observacao", "").strip()

        if not arquivo or arquivo.filename == "":
            flash("Selecione um arquivo para enviar.", "erro")
            return redirect(url_for("upload_comprovante", id=id))

        if not arquivo_permitido(arquivo.filename):
            flash("Formato inválido. Envie PNG, JPG, JPEG ou PDF.", "erro")
            return redirect(url_for("upload_comprovante", id=id))

        nome_seguro = secure_filename(arquivo.filename)
        nome_final = f"{datetime.utcnow().strftime('%Y%m%d%H%M%S')}_{nome_seguro}"
        caminho_arquivo = os.path.join(app.config["UPLOAD_FOLDER"], nome_final)
        arquivo.save(caminho_arquivo)

        comprovante = ComprovanteEntrega(
            rastreamento_id=carga.id,
            nome_arquivo=nome_final,
            observacao=observacao
        )

        db.session.add(comprovante)

        historico = HistoricoRastreamento(
            rastreamento_id=carga.id,
            status=carga.status,
            local=carga.local_atual,
            observacao="Comprovante de entrega anexado"
        )

        db.session.add(historico)
        db.session.commit()

        registrar_log(
    "Upload de comprovante",
    f"Comprovante enviado para a carga {carga.codigo}."
)

        flash("Comprovante enviado com sucesso!", "sucesso")
        return redirect(url_for("admin_rastreamento"))

    return render_template("upload_comprovante.html", carga=carga)

@app.route("/admin/rastreamentos/<int:id>/ocorrencia", methods=["GET", "POST"])
@login_obrigatorio
def nova_ocorrencia(id):
    carga = Rastreamento.query.get_or_404(id)

    if request.method == "POST":
        titulo = request.form.get("titulo", "").strip()
        descricao = request.form.get("descricao", "").strip()

        if not titulo or not descricao:
            flash("Preencha título e descrição da ocorrência.", "erro")
            return redirect(url_for("nova_ocorrencia", id=id))

        ocorrencia = OcorrenciaEntrega(
            rastreamento_id=carga.id,
            titulo=titulo,
            descricao=descricao
        )

        db.session.add(ocorrencia)

        historico = HistoricoRastreamento(
            rastreamento_id=carga.id,
            status=carga.status,
            local=carga.local_atual,
            observacao=f"Ocorrência registrada: {titulo}"
        )

        db.session.add(historico)
        db.session.commit()

        registrar_log(
    "Registro de ocorrência",
    f"Ocorrência registrada na carga {carga.codigo}: {titulo}."
)

        flash("Ocorrência registrada com sucesso!", "sucesso")
        return redirect(url_for("admin_rastreamento"))

    return render_template("nova_ocorrencia.html", carga=carga)

@app.route("/admin/clientes")
@login_obrigatorio
def admin_clientes():
    clientes = Cliente.query.order_by(Cliente.data_criacao.desc()).all()
    return render_template("admin_clientes.html", clientes=clientes)


@app.route("/admin/clientes/novo", methods=["GET", "POST"])
@login_obrigatorio
def novo_cliente():
    if request.method == "POST":

        # 🔹 DADOS DO CLIENTE
        razao_social = request.form.get("razao_social", "").strip()
        nome_fantasia = request.form.get("nome_fantasia", "").strip()
        documento = request.form.get("documento", "").strip()
        responsavel = request.form.get("responsavel", "").strip()
        email = request.form.get("email", "").strip().lower()
        telefone = request.form.get("telefone", "").strip()
        endereco = request.form.get("endereco", "").strip()
        cidade = request.form.get("cidade", "").strip()
        estado = request.form.get("estado", "").strip().upper()

        # 🔥 👉 COLE AQUI
        email_acesso = request.form.get("email_acesso", "").strip().lower()
        senha_acesso = request.form.get("senha_acesso", "").strip()

        if not razao_social:
            flash("Informe a razão social do cliente.", "erro")
            return redirect(url_for("novo_cliente"))

        cliente = Cliente(
            razao_social=razao_social,
            nome_fantasia=nome_fantasia,
            documento=documento,
            responsavel=responsavel,
            email=email,
            telefone=telefone,
            endereco=endereco,
            cidade=cidade,
            estado=estado,
            ativo=True
        )

        db.session.add(cliente)
        db.session.commit()

        # 🔥 CRIA LOGIN DO CLIENTE
        if email_acesso and senha_acesso:
            usuario_cliente = ClienteUsuario(
                cliente_id=cliente.id,
                nome=responsavel or razao_social,
                empresa=razao_social,
                email=email_acesso,
                senha=senha_acesso,
                ativo=True
            )

            db.session.add(usuario_cliente)
            db.session.commit()

        flash("Cliente cadastrado com sucesso!", "sucesso")
        return redirect(url_for("admin_clientes"))

    return render_template("novo_cliente.html")

    


@app.route("/admin/clientes/editar/<int:id>", methods=["GET", "POST"])
@login_obrigatorio
def editar_cliente(id):
    cliente = Cliente.query.get_or_404(id)

    if request.method == "POST":
        cliente.razao_social = request.form.get("razao_social", "").strip()
        cliente.nome_fantasia = request.form.get("nome_fantasia", "").strip()
        cliente.documento = request.form.get("documento", "").strip()
        cliente.responsavel = request.form.get("responsavel", "").strip()
        cliente.email = request.form.get("email", "").strip().lower()
        cliente.telefone = request.form.get("telefone", "").strip()
        cliente.endereco = request.form.get("endereco", "").strip()
        cliente.cidade = request.form.get("cidade", "").strip()
        cliente.estado = request.form.get("estado", "").strip().upper()
        cliente.ativo = True if request.form.get("ativo") == "on" else False

        if not cliente.razao_social:
            flash("Informe a razão social do cliente.", "erro")
            return redirect(url_for("editar_cliente", id=id))

        db.session.commit()

        flash("Cliente atualizado com sucesso!", "sucesso")
        return redirect(url_for("admin_clientes"))

    return render_template("editar_cliente.html", cliente=cliente)


@app.route("/admin/clientes/excluir/<int:id>", methods=["POST"])
@login_obrigatorio
def excluir_cliente(id):
    cliente = Cliente.query.get_or_404(id)

    db.session.delete(cliente)
    db.session.commit()

    flash("Cliente excluído com sucesso!", "sucesso")
    return redirect(url_for("admin_clientes"))

def adicionar_colunas_operacionais():
    import sqlite3

    conexao = sqlite3.connect(db_path)
    cursor = conexao.cursor()

    cursor.execute("PRAGMA table_info(rastreamento)")
    colunas_rastreamento = [coluna[1] for coluna in cursor.fetchall()]

    if "cliente_id" not in colunas_rastreamento:
        cursor.execute("ALTER TABLE rastreamento ADD COLUMN cliente_id INTEGER")
        conexao.commit()

    if "motorista_id" not in colunas_rastreamento:
        cursor.execute("ALTER TABLE rastreamento ADD COLUMN motorista_id INTEGER")
        conexao.commit()

    if "veiculo_id" not in colunas_rastreamento:
        cursor.execute("ALTER TABLE rastreamento ADD COLUMN veiculo_id INTEGER")
        conexao.commit()

    if "rota_id" not in colunas_rastreamento:
        cursor.execute("ALTER TABLE rastreamento ADD COLUMN rota_id INTEGER")
        conexao.commit()

    if "previsao_entrega" not in colunas_rastreamento:
        cursor.execute("ALTER TABLE rastreamento ADD COLUMN previsao_entrega DATETIME")
        conexao.commit()

    cursor.execute("PRAGMA table_info(cliente_usuario)")
    colunas_cliente_usuario = [coluna[1] for coluna in cursor.fetchall()]

    if "cliente_id" not in colunas_cliente_usuario:
        cursor.execute("ALTER TABLE cliente_usuario ADD COLUMN cliente_id INTEGER")
        conexao.commit()

        registrar_log(
    "Exclusão de cliente",
    "Cliente {cliente.razao_social} foi excluído."
)

        previsao_entrega_str = request.form.get("previsao_entrega", "").strip()

        cursor.execute("PRAGMA table_info(motorista)")
        colunas_motorista = [coluna[1] for coluna in cursor.fetchall()]

    if "usuario" not in colunas_motorista:
        cursor.execute("ALTER TABLE motorista ADD COLUMN usuario TEXT")
    conexao.commit()

    if "senha" not in colunas_motorista:
        cursor.execute("ALTER TABLE motorista ADD COLUMN senha TEXT")
        conexao.commit()

        cursor.execute("PRAGMA table_info(rastreamento)")
        colunas_rastreamento = [coluna[1] for coluna in cursor.fetchall()]


    if "destino_latitude" not in colunas_rastreamento:
     cursor.execute("ALTER TABLE rastreamento ADD COLUMN destino_latitude TEXT")
     conexao.commit()

    if "destino_longitude" not in colunas_rastreamento:
      cursor.execute("ALTER TABLE rastreamento ADD COLUMN destino_longitude TEXT")
    conexao.commit()


    conexao.close()

@app.route("/cliente/logout")
def cliente_logout():
    session.pop("cliente_logado", None)
    session.pop("cliente_id", None)
    session.pop("cliente_nome", None)
    session.pop("cliente_empresa", None)
    session.pop("cliente_id_ref", None)

    flash("Você saiu da área do cliente.", "sucesso")
    return redirect(url_for("cliente_login"))

@app.route("/admin/motoristas")
@login_obrigatorio
def admin_motoristas():
    motoristas = Motorista.query.order_by(Motorista.data_criacao.desc()).all()
    return render_template("admin_motoristas.html", motoristas=motoristas)


@app.route("/admin/motoristas/novo", methods=["GET", "POST"])
@login_obrigatorio
def novo_motorista():
    if request.method == "POST":
        motorista = Motorista(
            nome=request.form.get("nome", "").strip(),
            cpf=request.form.get("cpf", "").strip(),
            cnh=request.form.get("cnh", "").strip(),
            categoria_cnh=request.form.get("categoria_cnh", "").strip().upper(),
            validade_cnh=request.form.get("validade_cnh", "").strip(),
            telefone=request.form.get("telefone", "").strip(),
            email=request.form.get("email", "").strip().lower(),
            usuario=request.form.get("usuario", "").strip(),
            senha=request.form.get("senha", "").strip(),
            status=request.form.get("status", "Ativo").strip(),
            observacoes=request.form.get("observacoes", "").strip()
        )

        if not motorista.nome:
            flash("Informe o nome do motorista.", "erro")
            return redirect(url_for("novo_motorista"))

        db.session.add(motorista)
        db.session.commit()

        flash("Motorista cadastrado com sucesso!", "sucesso")
        return redirect(url_for("admin_motoristas"))

    return render_template("novo_motorista.html")


@app.route("/admin/motoristas/editar/<int:id>", methods=["GET", "POST"])
@login_obrigatorio
def editar_motorista(id):
    motorista = Motorista.query.get_or_404(id)

    if request.method == "POST":
        motorista.nome = request.form.get("nome", "").strip()
        motorista.cpf = request.form.get("cpf", "").strip()
        motorista.cnh = request.form.get("cnh", "").strip()
        motorista.categoria_cnh = request.form.get("categoria_cnh", "").strip().upper()
        motorista.validade_cnh = request.form.get("validade_cnh", "").strip()
        motorista.telefone = request.form.get("telefone", "").strip()
        motorista.email = request.form.get("email", "").strip().lower()
        motorista.usuario = request.form.get("usuario", "").strip()
        motorista.senha = request.form.get("senha", "").strip()
        motorista.status = request.form.get("status", "Ativo").strip()
        motorista.observacoes = request.form.get("observacoes", "").strip()

        if not motorista.nome:
            flash("Informe o nome do motorista.", "erro")
            return redirect(url_for("editar_motorista", id=id))

        db.session.commit()

        flash("Motorista atualizado com sucesso!", "sucesso")
        return redirect(url_for("admin_motoristas"))

    return render_template("editar_motorista.html", motorista=motorista)


@app.route("/admin/motoristas/excluir/<int:id>", methods=["POST"])
@login_obrigatorio
def excluir_motorista(id):
    motorista = Motorista.query.get_or_404(id)

    db.session.delete(motorista)
    db.session.commit()

    flash("Motorista excluído com sucesso!", "sucesso")
    return redirect(url_for("admin_motoristas"))

@app.route("/admin/veiculos")
@login_obrigatorio
def admin_veiculos():
    veiculos = Veiculo.query.order_by(Veiculo.data_criacao.desc()).all()
    return render_template("admin_veiculos.html", veiculos=veiculos)


@app.route("/admin/veiculos/novo", methods=["GET", "POST"])
@login_obrigatorio
def novo_veiculo():
    if request.method == "POST":
        placa = request.form.get("placa", "").strip().upper()

        if not placa:
            flash("Informe a placa do veículo.", "erro")
            return redirect(url_for("novo_veiculo"))

        existente = Veiculo.query.filter_by(placa=placa).first()
        if existente:
            flash("Já existe um veículo cadastrado com esta placa.", "erro")
            return redirect(url_for("novo_veiculo"))

        veiculo = Veiculo(
            placa=placa,
            modelo=request.form.get("modelo", "").strip(),
            marca=request.form.get("marca", "").strip(),
            tipo=request.form.get("tipo", "").strip(),
            ano=request.form.get("ano", "").strip(),
            capacidade=request.form.get("capacidade", "").strip(),
            status=request.form.get("status", "Disponível").strip(),
            observacoes=request.form.get("observacoes", "").strip()
        )

        db.session.add(veiculo)
        db.session.commit()

        flash("Veículo cadastrado com sucesso!", "sucesso")
        return redirect(url_for("admin_veiculos"))

    return render_template("novo_veiculo.html")


@app.route("/admin/veiculos/editar/<int:id>", methods=["GET", "POST"])
@login_obrigatorio
def editar_veiculo(id):
    veiculo = Veiculo.query.get_or_404(id)

    if request.method == "POST":
        nova_placa = request.form.get("placa", "").strip().upper()

        duplicado = Veiculo.query.filter(
            Veiculo.placa == nova_placa,
            Veiculo.id != veiculo.id
        ).first()

        if duplicado:
            flash("Já existe outro veículo com esta placa.", "erro")
            return redirect(url_for("editar_veiculo", id=id))

        if not nova_placa:
            flash("Informe a placa do veículo.", "erro")
            return redirect(url_for("editar_veiculo", id=id))

        veiculo.placa = nova_placa
        veiculo.modelo = request.form.get("modelo", "").strip()
        veiculo.marca = request.form.get("marca", "").strip()
        veiculo.tipo = request.form.get("tipo", "").strip()
        veiculo.ano = request.form.get("ano", "").strip()
        veiculo.capacidade = request.form.get("capacidade", "").strip()
        veiculo.status = request.form.get("status", "Disponível").strip()
        veiculo.observacoes = request.form.get("observacoes", "").strip()

        db.session.commit()

        flash("Veículo atualizado com sucesso!", "sucesso")
        return redirect(url_for("admin_veiculos"))

    return render_template("editar_veiculo.html", veiculo=veiculo)


@app.route("/admin/veiculos/excluir/<int:id>", methods=["POST"])
@login_obrigatorio
def excluir_veiculo(id):
    veiculo = Veiculo.query.get_or_404(id)

    db.session.delete(veiculo)
    db.session.commit()

    flash("Veículo excluído com sucesso!", "sucesso")
    return redirect(url_for("admin_veiculos"))

from math import radians, sin, cos, sqrt, atan2
from datetime import timedelta

def calcular_distancia_km(lat1, lon1, lat2, lon2):
    raio_terra_km = 6371

    lat1 = radians(float(lat1))
    lon1 = radians(float(lon1))
    lat2 = radians(float(lat2))
    lon2 = radians(float(lon2))

    dlat = lat2 - lat1
    dlon = lon2 - lon1

    a = sin(dlat / 2) ** 2 + cos(lat1) * cos(lat2) * sin(dlon / 2) ** 2
    c = 2 * atan2(sqrt(a), sqrt(1 - a))

    return raio_terra_km * c


def calcular_eta(carga, velocidade_media_kmh=60):
    ultima_localizacao = LocalizacaoMotorista.query.filter_by(
        rastreamento_id=carga.id
    ).order_by(LocalizacaoMotorista.data_registro.desc()).first()

    if not ultima_localizacao:
        return None, None

    if not carga.destino_latitude or not carga.destino_longitude:
        return None, None

    distancia_km = calcular_distancia_km(
        ultima_localizacao.latitude,
        ultima_localizacao.longitude,
        carga.destino_latitude,
        carga.destino_longitude
    )

    horas = distancia_km / velocidade_media_kmh
    eta = datetime.utcnow() + timedelta(hours=horas)

    return distancia_km, eta

@app.route("/admin/rotas")
@login_obrigatorio
def admin_rotas():
    rotas = Rota.query.filter_by(status="Ativa").order_by(Rota.nome.asc()).all()
    rotas = Rota.query.order_by(Rota.data_criacao.desc()).all()
    return render_template("admin_rotas.html", rotas=rotas )

def registrar_log(acao, detalhes=""):
    usuario_id = session.get("usuario_sistema_id")
    usuario_nome = session.get("usuario_sistema_nome")

    log = LogAcao(
        usuario_id=usuario_id,
        usuario_nome=usuario_nome,
        acao=acao,
        detalhes=detalhes
    )

    db.session.add(log)
    db.session.commit()

@app.route("/admin/rotas/nova", methods=["GET", "POST"])
@login_obrigatorio
def nova_rota():
    if request.method == "POST": 
        nome = request.form.get("nome", "").strip()
        origem = request.form.get("origem", "").strip()
        destino = request.form.get("destino", "").strip()

        if not all([nome, origem, destino]):
            flash("Informe nome, origem e destino da rota.", "erro")
            return redirect(url_for("nova_rota"))

        rota = Rota(
            nome=nome,
            origem=origem,
            destino=destino,
            distancia=request.form.get("distancia", "").strip(),
            previsao_tempo=request.form.get("previsao_tempo", "").strip(),
            pedagio_estimado=request.form.get("pedagio_estimado", "").strip(),
            observacoes=request.form.get("observacoes", "").strip(),
            status=request.form.get("status", "Ativa").strip()
        )

        db.session.add(rota)
        db.session.commit()

        flash("Rota cadastrada com sucesso!", "sucesso")
        return redirect(url_for("admin_rotas"))

    return render_template("nova_rota.html")


@app.route("/admin/rotas/editar/<int:id>", methods=["GET", "POST"])
@login_obrigatorio
def editar_rota(id):
    rota = Rota.query.get_or_404(id)

    if request.method == "POST":
        rota.nome = request.form.get("nome", "").strip()
        rota.origem = request.form.get("origem", "").strip()
        rota.destino = request.form.get("destino", "").strip()
        rota.distancia = request.form.get("distancia", "").strip()
        rota.previsao_tempo = request.form.get("previsao_tempo", "").strip()
        rota.pedagio_estimado = request.form.get("pedagio_estimado", "").strip()
        rota.observacoes = request.form.get("observacoes", "").strip()
        rota.status = request.form.get("status", "Ativa").strip()

        if not all([rota.nome, rota.origem, rota.destino]):
            flash("Informe nome, origem e destino da rota.", "erro")
            return redirect(url_for("editar_rota", id=id))

        db.session.commit()

        flash("Rota atualizada com sucesso!", "sucesso")
        return redirect(url_for("admin_rotas"))

    return render_template("editar_rota.html", rota=rota)


@app.route("/admin/rotas/excluir/<int:id>", methods=["POST"])
@login_obrigatorio
def excluir_rota(id):
    rota = Rota.query.get_or_404(id)

    db.session.delete(rota)
    db.session.commit()

    flash("Rota excluída com sucesso!", "sucesso")
    return redirect(url_for("admin_rotas"))

@app.route("/admin/novo_rastreamento", methods=["GET", "POST"])
@login_obrigatorio
def novo_rastreamento():
    clientes = Cliente.query.filter_by(ativo=True).order_by(Cliente.razao_social.asc()).all()
    motoristas = Motorista.query.filter_by(status="Ativo").order_by(Motorista.nome.asc()).all()
    veiculos = Veiculo.query.order_by(Veiculo.placa.asc()).all()
    rotas = Rota.query.filter_by(status="Ativa").order_by(Rota.nome.asc()).all()
    if request.method == "POST":
        codigo = request.form.get("codigo", "").strip().upper()
        cliente_id = request.form.get("cliente_id", "").strip()
        motorista_id = request.form.get("motorista_id", "").strip()
        veiculo_id = request.form.get("veiculo_id", "").strip()
        rota_id = request.form.get("rota_id", "").strip()
        status = request.form.get("status", "").strip()
        local_atual = request.form.get("local_atual", "").strip()
        destino = request.form.get("destino", "").strip()
        previsao_entrega_str = request.form.get("previsao_entrega", "").strip()
        destino_latitude = request.form.get("destino_latitude", "").strip()
        destino_longitude = request.form.get("destino_longitude", "").strip()
        previsao_entrega = None
        if previsao_entrega_str:
            previsao_entrega = datetime.strptime(previsao_entrega_str, "%Y-%m-%dT%H:%M")

        if not all([codigo, cliente_id, status, local_atual, destino]):
            flash("Preencha os campos obrigatórios do rastreamento.", "erro")
            return redirect(url_for("novo_rastreamento"))

        cliente_obj = Cliente.query.get(cliente_id)

        if not cliente_obj:
            flash("Cliente não encontrado.", "erro")
            return redirect(url_for("novo_rastreamento"))

        existente = Rastreamento.query.filter_by(codigo=codigo).first()
        if existente:
            flash("Já existe um rastreamento com esse código.", "erro")
            return redirect(url_for("novo_rastreamento"))

        nova_carga = Rastreamento(
            codigo=codigo,
            cliente_id=cliente_obj.id,
            cliente=cliente_obj.razao_social,
            motorista_id=int(motorista_id) if motorista_id else None,
            veiculo_id=int(veiculo_id) if veiculo_id else None,
            rota_id=int(rota_id) if rota_id else None,
            destino_latitude=destino_latitude,
            destino_longitude=destino_longitude,    
            previsao_entrega=previsao_entrega,
            status=status,
            local_atual=local_atual,
            destino=destino,
            ultima_atualizacao=datetime.utcnow()
        )

        db.session.add(nova_carga)
        db.session.commit()

        historico = HistoricoRastreamento(
            rastreamento_id=nova_carga.id,
            status=nova_carga.status,
            local=nova_carga.local_atual,
            observacao="Carga cadastrada no sistema"
        )

        db.session.add(historico)
        db.session.commit()

        registrar_log(
    "Cadastro de rastreamento",
    f"Carga {nova_carga.codigo} cadastrada para o cliente {nova_carga.cliente}."
)

        flash("Rastreamento cadastrado com sucesso!", "sucesso")
        return redirect(url_for("admin_rastreamento"))

    return render_template(
        "novo_rastreamento.html",
        clientes=clientes,
        motoristas=motoristas,
        veiculos=veiculos,
        rotas=rotas
    )

@app.route("/admin/logs")
@login_obrigatorio
def admin_logs():
    logs = LogAcao.query.order_by(LogAcao.data_acao.desc()).limit(200).all()
    return render_template("admin_logs.html", logs=logs)

@app.route("/admin/relatorios", methods=["GET", "POST"])
@login_obrigatorio
def admin_relatorios():
    clientes = Cliente.query.order_by(Cliente.razao_social.asc()).all()
    motoristas = Motorista.query.order_by(Motorista.nome.asc()).all()

    cargas = []
    total = 0
    entregues = 0
    em_transito = 0
    atrasadas = 0

    if request.method == "POST":
        data_inicio = request.form.get("data_inicio", "").strip()
        data_fim = request.form.get("data_fim", "").strip()
        cliente_id = request.form.get("cliente_id", "").strip()
        motorista_id = request.form.get("motorista_id", "").strip()
        status = request.form.get("status", "").strip()

        consulta = Rastreamento.query

        if data_inicio:
            inicio = datetime.strptime(data_inicio, "%Y-%m-%d")
            consulta = consulta.filter(Rastreamento.ultima_atualizacao >= inicio)

        if data_fim:
            fim = datetime.strptime(data_fim, "%Y-%m-%d")
            fim = fim.replace(hour=23, minute=59, second=59)
            consulta = consulta.filter(Rastreamento.ultima_atualizacao <= fim)

        if cliente_id:
            consulta = consulta.filter(Rastreamento.cliente_id == int(cliente_id))

        if motorista_id:
            consulta = consulta.filter(Rastreamento.motorista_id == int(motorista_id))

        if status:
            consulta = consulta.filter(Rastreamento.status == status)

        cargas = consulta.order_by(Rastreamento.ultima_atualizacao.desc()).all()

        total = len(cargas)
        entregues = len([c for c in cargas if c.status == "Entregue"])
        em_transito = len([c for c in cargas if c.status == "Em trânsito"])

        agora = datetime.utcnow()
        atrasadas = len([
            c for c in cargas
            if c.previsao_entrega and c.previsao_entrega < agora and c.status != "Entregue"
        ])

    return render_template(
        "admin_relatorios.html",
        clientes=clientes,
        motoristas=motoristas,
        cargas=cargas,
        total=total,
        entregues=entregues,
        em_transito=em_transito,
        atrasadas=atrasadas
    )

@app.route("/admin/mapa/<int:id>")
@login_obrigatorio
def admin_mapa_carga(id):
    carga = Rastreamento.query.get_or_404(id)

    localizacoes = LocalizacaoMotorista.query.filter_by(
        rastreamento_id=id
    ).order_by(LocalizacaoMotorista.data_registro.desc()).all()

    return render_template(
        "admin_mapa_carga.html",
        carga=carga,
        localizacoes=localizacoes
    )

@app.route("/motorista/login", methods=["GET", "POST"])
def motorista_login():
    if request.method == "POST":
        usuario = request.form.get("usuario", "").strip()
        senha = request.form.get("senha", "").strip()

        motorista = Motorista.query.filter_by(
            usuario=usuario,
            senha=senha,
            status="Ativo"
        ).first()

        if motorista:
            session["motorista_logado"] = True
            session["motorista_id"] = motorista.id
            session["motorista_nome"] = motorista.nome

            flash("Login do motorista realizado com sucesso!", "sucesso")
            return redirect(url_for("motorista_painel"))

        flash("Usuário ou senha inválidos.", "erro")

    return render_template("motorista_login.html")


@app.route("/motorista/logout")
def motorista_logout():
    session.pop("motorista_logado", None)
    session.pop("motorista_id", None)
    session.pop("motorista_nome", None)

    flash("Você saiu da área do motorista.", "sucesso")
    return redirect(url_for("motorista_login"))


@app.route("/motorista/painel")
@motorista_login_obrigatorio
def motorista_painel():
    motorista_id = session.get("motorista_id")

    cargas = Rastreamento.query.filter_by(
        motorista_id=motorista_id
    ).order_by(Rastreamento.ultima_atualizacao.desc()).all()

    total = len(cargas)
    em_transito = len([c for c in cargas if c.status == "Em trânsito"])
    entregues = len([c for c in cargas if c.status == "Entregue"])
    ocorrencias = OcorrenciaEntrega.query.join(Rastreamento).filter(
        Rastreamento.motorista_id == motorista_id
    ).count()

    return render_template(
        "motorista_painel.html",
        cargas=cargas,
        total=total,
        em_transito=em_transito,
        entregues=entregues,
        ocorrencias=ocorrencias
    )

@app.route("/motorista/carga/<int:id>", methods=["GET", "POST"])
@motorista_login_obrigatorio
def motorista_carga_detalhe(id):
    carga = Rastreamento.query.get_or_404(id)

    if carga.motorista_id != session.get("motorista_id"):
        flash("Acesso não autorizado.", "erro")
        return redirect(url_for("motorista_painel"))

    if request.method == "POST":
        novo_status = request.form.get("status", "").strip()
        local_atual = request.form.get("local_atual", "").strip()
        observacao = request.form.get("observacao", "").strip()

        if not novo_status or not local_atual:
            flash("Informe status e local atual.", "erro")
            return redirect(url_for("motorista_carga_detalhe", id=id))

        carga.status = novo_status
        carga.local_atual = local_atual
        carga.ultima_atualizacao = datetime.utcnow()

        historico = HistoricoRastreamento(
            rastreamento_id=carga.id,
            status=carga.status,
            local=carga.local_atual,
            observacao=observacao or "Atualização feita pelo motorista"
        )

        db.session.add(historico)
        db.session.commit()

        flash("Carga atualizada com sucesso!", "sucesso")
        return redirect(url_for("motorista_painel"))

    historico = HistoricoRastreamento.query.filter_by(
        rastreamento_id=id
    ).order_by(HistoricoRastreamento.data_evento.desc()).all()

    localizacoes = LocalizacaoMotorista.query.filter_by(
    rastreamento_id=id
    ).order_by(LocalizacaoMotorista.data_registro.desc()).all()

    return render_template(
        "motorista_carga_detalhe.html",
        carga=carga,
        historico=historico,
        localizacoes=localizacoes
    )

def adicionar_colunas_operacionais():
    import sqlite3

    conexao = sqlite3.connect(db_path)
    cursor = conexao.cursor()

    # TABELA RASTREAMENTO
    cursor.execute("PRAGMA table_info(rastreamento)")
    colunas_rastreamento = [coluna[1] for coluna in cursor.fetchall()]

    if "cliente_id" not in colunas_rastreamento:
        cursor.execute("ALTER TABLE rastreamento ADD COLUMN cliente_id INTEGER")
        conexao.commit()

    if "motorista_id" not in colunas_rastreamento:
        cursor.execute("ALTER TABLE rastreamento ADD COLUMN motorista_id INTEGER")
        conexao.commit()

    if "veiculo_id" not in colunas_rastreamento:
        cursor.execute("ALTER TABLE rastreamento ADD COLUMN veiculo_id INTEGER")
        conexao.commit()

    if "rota_id" not in colunas_rastreamento:
        cursor.execute("ALTER TABLE rastreamento ADD COLUMN rota_id INTEGER")
        conexao.commit()

    if "previsao_entrega" not in colunas_rastreamento:
        cursor.execute("ALTER TABLE rastreamento ADD COLUMN previsao_entrega DATETIME")
        conexao.commit()

    if "destino_latitude" not in colunas_rastreamento:
        cursor.execute("ALTER TABLE rastreamento ADD COLUMN destino_latitude TEXT")
        conexao.commit()

    if "destino_longitude" not in colunas_rastreamento:
        cursor.execute("ALTER TABLE rastreamento ADD COLUMN destino_longitude TEXT")
        conexao.commit()

    # TABELA CLIENTE_USUARIO
    cursor.execute("PRAGMA table_info(cliente_usuario)")
    colunas_cliente_usuario = [coluna[1] for coluna in cursor.fetchall()]

    if "cliente_id" not in colunas_cliente_usuario:
        cursor.execute("ALTER TABLE cliente_usuario ADD COLUMN cliente_id INTEGER")
        conexao.commit()

    # TABELA MOTORISTA
    cursor.execute("PRAGMA table_info(motorista)")
    colunas_motorista = [coluna[1] for coluna in cursor.fetchall()]

    if "usuario" not in colunas_motorista:
        cursor.execute("ALTER TABLE motorista ADD COLUMN usuario TEXT")
        conexao.commit()

    if "senha" not in colunas_motorista:
        cursor.execute("ALTER TABLE motorista ADD COLUMN senha TEXT")
        conexao.commit()

    conexao.close()

@app.route("/motorista/localizacao/<int:id>", methods=["POST"])
@motorista_login_obrigatorio
def salvar_localizacao(id):
    dados = request.get_json()

    latitude = dados.get("latitude")
    longitude = dados.get("longitude")

    motorista_id = session.get("motorista_id")

    local = LocalizacaoMotorista(
        motorista_id=motorista_id,
        rastreamento_id=id,
        latitude=latitude,
        longitude=longitude
    )

    db.session.add(local)
    db.session.commit()

    return {"status": "ok"}

@app.route("/admin/carga/<int:id>")
@login_obrigatorio
def admin_carga_detalhe(id):
    carga = Rastreamento.query.get_or_404(id)

    historico = HistoricoRastreamento.query.filter_by(
        rastreamento_id=id
    ).order_by(HistoricoRastreamento.data_evento.desc()).all()

    comprovantes = ComprovanteEntrega.query.filter_by(
        rastreamento_id=id
    ).order_by(ComprovanteEntrega.data_upload.desc()).all()

    ocorrencias = OcorrenciaEntrega.query.filter_by(
        rastreamento_id=id
    ).order_by(OcorrenciaEntrega.data_ocorrencia.desc()).all()

    localizacoes = LocalizacaoMotorista.query.filter_by(
        rastreamento_id=id
    ).order_by(LocalizacaoMotorista.data_registro.desc()).all()

    distancia_restante, eta_estimado = calcular_eta(carga)

    return render_template(
        "admin_carga_detalhe.html",
        carga=carga,
        historico=historico,
        comprovantes=comprovantes,
        ocorrencias=ocorrencias,
        localizacoes=localizacoes,
        distancia_restante=distancia_restante,
        eta_estimado=eta_estimado,
        now=datetime.utcnow()
    )

with app.app_context():
    db.create_all()
    adicionar_colunas_operacionais()

    admin_padrao = UsuarioSistema.query.filter_by(usuario="admin").first()

    if not admin_padrao:
        admin_padrao = UsuarioSistema(
            nome="Administrador",
            usuario="admin",
            senha="ramos123",
            perfil="administrador",
            ativo=True
        )

        db.session.add(admin_padrao)
        db.session.commit()


@app.route("/api/teste")
def api_teste():
    return {"mensagem": "API Flask conectada com sucesso!"}

@app.route("/api/cotacoes", methods=["POST"])
def api_criar_cotacao():
    dados = request.get_json()

    cliente = dados.get("cliente", "").strip()
    whatsapp = dados.get("whatsapp", "").strip()
    origem = dados.get("origem", "").strip()
    destino = dados.get("destino", "").strip()
    tipo_carga = dados.get("tipoCarga", "").strip()
    observacoes = dados.get("observacoes", "").strip()

    if not all([cliente, whatsapp, origem, destino, tipo_carga]):
        return {"erro": "Preencha todos os campos obrigatórios."}, 400

    nova_cotacao = Cotacao(
        cliente=cliente,
        whatsapp=whatsapp,
        origem=origem,
        destino=destino,
        tipo_carga=tipo_carga,
        observacoes=observacoes
    )

    db.session.add(nova_cotacao)
    db.session.commit()

    return {
        "mensagem": "Orçamento enviado com sucesso!",
        "cotacao_id": nova_cotacao.id
    }, 201
    
@app.route("/api/rastreamento/<codigo>", methods=["GET"])
def api_buscar_rastreamento(codigo):
    codigo = codigo.strip().upper()

    carga = Rastreamento.query.filter_by(codigo=codigo).first()

    if not carga:
        return {"erro": "Código de rastreamento não encontrado."}, 404

    ultima_atualizacao = ""
    if carga.ultima_atualizacao:
        ultima_atualizacao = carga.ultima_atualizacao.strftime("%d/%m/%Y %H:%M")

    return {
        "id": carga.id,
        "codigo": carga.codigo,
        "cliente": carga.cliente,
        "status": carga.status,
        "local_atual": carga.local_atual,
        "destino": carga.destino,
        "ultima_atualizacao": ultima_atualizacao
    }, 200
    
@app.route("/api/dev/criar-rastreamento", methods=["POST"])
def api_dev_criar_rastreamento():
    nova_carga = Rastreamento(
        codigo="RAM001",
        cliente="Cliente Teste React",
        status="Em trânsito",
        local_atual="São José do Rio Preto/SP",
        destino="Goiânia/GO",
        ultima_atualizacao=datetime.utcnow()
    )

    db.session.add(nova_carga)
    db.session.commit()

    return {"mensagem": "Rastreamento RAM001 criado com sucesso."
    }, 201
    
@app.route("/api/login", methods=["POST"])
def api_login():
    dados = request.get_json()

    usuario = dados.get("usuario", "").strip()
    senha = dados.get("senha", "").strip()

    usuario_sistema = UsuarioSistema.query.filter_by(
        usuario=usuario,
        senha=senha,
        ativo=True
    ).first()

    if not usuario_sistema:
        return {
            "erro": "Usuário ou senha inválidos."
        }, 401

    return {
        "mensagem": "Login realizado com sucesso!",
        "usuario": {
            "id": usuario_sistema.id,
            "nome": usuario_sistema.nome,
            "perfil": usuario_sistema.perfil
        }
    }, 200
    
@app.route("/api/admin/resumo", methods=["GET"])
def api_admin_resumo():
    total_cargas = Rastreamento.query.count()
    em_coleta = Rastreamento.query.filter_by(status="Em coleta").count()
    em_transito = Rastreamento.query.filter_by(status="Em trânsito").count()
    saiu_entrega = Rastreamento.query.filter_by(status="Saiu para entrega").count()
    entregues = Rastreamento.query.filter_by(status="Entregue").count()
    total_cotacoes = Cotacao.query.count()

    agora = datetime.utcnow()

    atrasadas = Rastreamento.query.filter(
        Rastreamento.previsao_entrega != None,
        Rastreamento.previsao_entrega < agora,
        Rastreamento.status != "Entregue"
    ).count()

    return {
        "total_cargas": total_cargas,
        "em_coleta": em_coleta,
        "em_transito": em_transito,
        "saiu_entrega": saiu_entrega,
        "entregues": entregues,
        "atrasadas": atrasadas,
        "total_cotacoes": total_cotacoes
    }
    
@app.route("/api/admin/cargas", methods=["GET"])
def api_admin_cargas():
    cargas = Rastreamento.query.order_by(
        Rastreamento.ultima_atualizacao.desc()
    ).all()

    lista = []

    for carga in cargas:
        lista.append({
            "id": carga.id,
            "codigo": carga.codigo,
            "cliente": carga.cliente,
            "status": carga.status,
            "local_atual": carga.local_atual,
            "destino": carga.destino
        })

    return lista

@app.route("/api/carga/<int:id>", methods=["GET"])
def api_carga_detalhe(id):
    carga = Rastreamento.query.get_or_404(id)

    ultima_atualizacao = ""
    if carga.ultima_atualizacao:
        ultima_atualizacao = carga.ultima_atualizacao.strftime("%d/%m/%Y %H:%M")

    return {
        "id": carga.id,
        "codigo": carga.codigo,
        "cliente": carga.cliente,
        "status": carga.status,
        "local_atual": carga.local_atual,
        "destino": carga.destino,
        "ultima_atualizacao": ultima_atualizacao
    }
    
@app.route("/api/admin/cargas", methods=["POST"])
def api_criar_carga():
    dados = request.get_json()

    codigo = dados.get("codigo", "").strip().upper()
    cliente = dados.get("cliente", "").strip()
    status = dados.get("status", "").strip()
    local_atual = dados.get("local_atual", "").strip()
    destino = dados.get("destino", "").strip()

    if not all([codigo, cliente, status, local_atual, destino]):
        return {"erro": "Preencha todos os campos obrigatórios."}, 400

    existente = Rastreamento.query.filter_by(codigo=codigo).first()

    if existente:
        return {"erro": "Já existe uma carga com esse código."}, 400

    nova_carga = Rastreamento(
        codigo=codigo,
        cliente=cliente,
        status=status,
        local_atual=local_atual,
        destino=destino,
        ultima_atualizacao=datetime.utcnow()
    )

    db.session.add(nova_carga)
    db.session.commit()

    return {
        "mensagem": "Carga criada com sucesso!",
        "id": nova_carga.id
    }, 201
    
if __name__ == "__main__":
  app.run(debug=True)