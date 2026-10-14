"""Repositório Shakyra — aplicação Flask.

Funciona em execução local (`python app.py`) e no runtime Python da Vercel,
que deteta automaticamente o entrypoint `app.py` deste repositório.
"""

import hashlib
import hmac
import json
import os
import unicodedata
from pathlib import Path
from urllib.parse import quote, unquote

from flask import (
    Flask,
    Response,
    abort,
    redirect,
    render_template,
    request,
    send_file,
    session,
    stream_with_context,
    url_for,
)
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer

REPO_DIR = Path(__file__).parent.resolve()
DOCS_HTML_DIR = REPO_DIR / "docs_html"
TEMPLATES_DIR = REPO_DIR / "templates"
ORIGINALS_DIR = REPO_DIR / "originals"
USERS_FILE = REPO_DIR / "users.json"
ZIP_FILE = REPO_DIR / "shakyra_completo.zip"

DEFAULT_USERS = {
    "admin": {"password": "admin_master_2026", "role": "admin"},
    "user1": {"password": "temp_user_pass_1", "role": "user"},
}

DOWNLOAD_PASSWORD = "download_secure_2026"

TMP_DIR = Path(os.environ.get("TMPDIR") or "/tmp")
TMP_USERS_FILE = TMP_DIR / "shakyra_users.json"

STREAM_THRESHOLD = 3 * 1024 * 1024
CHUNK_SIZE = 256 * 1024

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "shakyra_secure_repository_secret_key_2026")


def _is_dir_writable(directory):
    return directory.is_dir() and os.access(directory, os.W_OK)


def _resolve_users_file():
    """Escolhe o ficheiro de utilizadores gravável (projeto ou /tmp)."""
    for candidate in (USERS_FILE, TMP_USERS_FILE):
        if not _is_dir_writable(candidate.parent):
            continue
        if not candidate.exists():
            seed = USERS_FILE if USERS_FILE.exists() else None
            payload = (
                seed.read_text(encoding="utf-8", errors="ignore")
                if seed
                else json.dumps(DEFAULT_USERS, indent=4, ensure_ascii=False)
            )
            try:
                candidate.write_text(payload, encoding="utf-8")
            except OSError:
                continue
        return candidate
    return USERS_FILE


USERS_STORE = _resolve_users_file()


def load_users():
    """Carrega os utilizadores dando prioridade aos ficheiros modificados."""
    for path in (TMP_USERS_FILE, USERS_STORE, USERS_FILE):
        if not path.is_file():
            continue
        try:
            users = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(users, dict) and users:
                return users
        except (OSError, ValueError):
            continue
    return dict(DEFAULT_USERS)


def save_users(users):
    """Guarda os utilizadores no armazenamento disponível."""
    payload = json.dumps(users, indent=4, ensure_ascii=False)
    saved = False
    for path in (TMP_USERS_FILE, USERS_STORE, USERS_FILE):
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(payload, encoding="utf-8")
            saved = True
        except OSError:
            continue
    return saved


def _get_serializer():
    return URLSafeTimedSerializer(app.secret_key, salt="shakyra_access_token")


def generate_access_token(username, role="user"):
    s = _get_serializer()
    return s.dumps({"user": username, "role": role})


def verify_access_token(token, max_age=30 * 86400):
    """Valida token com validade máxima de até 30 dias."""
    s = _get_serializer()
    try:
        data = s.loads(token, max_age=max_age)
        return data
    except (SignatureExpired, BadSignature, Exception):
        return None


def generate_temp_password(username):
    """Gera senha temporária determinística que funciona sempre em serverless."""
    clean_user = username.lower().strip()
    h = hmac.new(app.secret_key.encode(), clean_user.encode(), hashlib.sha256).hexdigest()[:8]
    return f"temp_{h}"


def is_valid_temp_password(username, password):
    """Verifica se a senha temporária fornecida corresponde ao HMAC assinado."""
    if not username or not password:
        return False
    expected = generate_temp_password(username)
    return hmac.compare_digest(password.strip(), expected)


def _doc_files():
    if not DOCS_HTML_DIR.is_dir():
        return []
    return sorted(
        (f.name for f in DOCS_HTML_DIR.glob("*.html")),
        key=lambda name: name.casefold(),
    )


def _original_files():
    if not ORIGINALS_DIR.is_dir():
        return []
    return sorted(
        (f.name for f in ORIGINALS_DIR.glob("*.*") if f.is_file() and not f.name.startswith("~$")),
        key=lambda name: name.casefold(),
    )


def _categorize(name):
    lower = name.lower()
    if "shakyra" in lower or "universidade" in lower or "relatorio_fonte_referencia" in lower:
        return "Monografia & Referência"
    if any(k in lower for k in ["relatorio_0", "base_dados", "planilha", "apresentacao"]):
        return "Relatórios Principais & Estratégicos"
    if any(k in lower for k in ["dr_", "dra_", "eng_", "sr_"]):
        return "Inquéritos Individuais (Respondentes Chave)"
    if "tom_a" in lower or "tom_b" in lower or "dois_tons" in lower:
        return "Inquéritos por Tom Separado"
    if any(k in lower for k in ["inquerito_rf", "inquerito_rreg", "inquerito_rsc", "relatorio_inquerito_rsc"]):
        return "Painel Completo N=35 (Transportadoras e Reguladores)"
    if any(k in lower for k in ["cfm", "ine", "petromoc", "worldbank"]):
        return "Portais Oficiais & Fontes Externas"
    return "Outros Documentos"


def _get_doc_items():
    files = _doc_files()
    items = []
    for idx, fname in enumerate(files):
        title = fname.removesuffix(".html").replace("_", " ")
        fpath = DOCS_HTML_DIR / fname
        size_kb = round(fpath.stat().st_size / 1024, 1) if fpath.exists() else 0
        items.append({
            "id": idx,
            "filename": fname,
            "title": title,
            "category": _categorize(fname),
            "size_kb": size_kb,
        })
    return items


def _get_original_items():
    files = _original_files()
    items = []
    for idx, fname in enumerate(files):
        fpath = ORIGINALS_DIR / fname
        size_kb = round(fpath.stat().st_size / 1024, 1) if fpath.exists() else 0
        ext = fpath.suffix.lower().replace(".", "").upper()
        title = fpath.stem.replace("_", " ")
        items.append({
            "id": idx,
            "filename": fname,
            "title": title,
            "category": _categorize(fname),
            "ext": ext,
            "size_kb": size_kb,
        })
    return items


def _resolve_target_file(directory, identifier, file_list):
    """Localiza o ficheiro pretendido de forma segura e flexível por ID numérico ou nome."""
    directory = directory.resolve()
    
    # 1. Se for ID numérico (ex: 0, 1, 2)
    if identifier.isdigit():
        idx = int(identifier)
        if 0 <= idx < len(file_list):
            candidate = directory / file_list[idx]
            if candidate.is_file():
                return candidate

    # 2. Tentativa direta com o nome e variantes descodificadas (URL unquote)
    raw = identifier
    dec1 = unquote(raw)
    dec2 = unquote(dec1)
    for cand_name in (raw, dec1, dec2):
        candidate = (directory / cand_name).resolve()
        if candidate.parent == directory and candidate.is_file():
            return candidate

    # 3. Comparação com tolerância a codificação Unicode (NFC vs NFD) e maiúsculas/minúsculas
    targets = set()
    for name in (raw, dec1, dec2):
        targets.add(unicodedata.normalize("NFC", name).casefold())
        targets.add(unicodedata.normalize("NFD", name).casefold())

    for f in directory.iterdir():
        if not f.is_file():
            continue
        fn_c = unicodedata.normalize("NFC", f.name).casefold()
        fn_d = unicodedata.normalize("NFD", f.name).casefold()
        if fn_c in targets or fn_d in targets:
            return f

    abort(404)


def _content_disposition(filename):
    fallback = filename.encode("ascii", "ignore").decode("ascii").replace('"', "").strip()
    if not fallback:
        fallback = "documento"
    return 'attachment; filename="%s"; filename*=UTF-8\'\'%s' % (fallback, quote(filename, safe=""))


def _file_response(path):
    """Devolve o ficheiro; usa streaming quando é grande (limite da Vercel)."""
    size = path.stat().st_size
    if size <= STREAM_THRESHOLD:
        return send_file(path, as_attachment=True, download_name=path.name)

    def generate():
        with path.open("rb") as handle:
            while True:
                chunk = handle.read(CHUNK_SIZE)
                if not chunk:
                    break
                yield chunk

    response = Response(stream_with_context(generate()), mimetype="application/octet-stream")
    response.headers["Content-Length"] = str(size)
    response.headers["Content-Disposition"] = _content_disposition(path.name)
    return response


@app.route("/")
def index():
    if "user" not in session:
        return redirect(url_for("login"))
    return redirect(url_for("dashboard"))


@app.route("/login", methods=["GET", "POST"])
def login():
    # 1. Acesso automático com token de convite no URL (?token=... ou ?access=...)
    token = request.args.get("token") or request.args.get("access")
    if token:
        data = verify_access_token(token)
        if data and "user" in data:
            session["user"] = data["user"]
            session["role"] = data.get("role", "user")
            return redirect(url_for("dashboard"))
        error = "O link de acesso expirou ou é inválido. Solicite novas credenciais ao administrador."
        return render_template("login.html", error=error)

    error = None
    if request.method == "POST":
        username = (request.form.get("username") or "").strip()
        password = request.form.get("password") or ""
        users = load_users()
        account = users.get(username)
        
        authenticated = False
        user_role = "user"
        
        # Validação normal de utilizador registado
        if account and account.get("password") == password:
            authenticated = True
            user_role = account.get("role", "user")
        # Validação por senha temporária assinada determinística (sempre funcional em serverless)
        elif is_valid_temp_password(username, password):
            authenticated = True
            user_role = "user"
            # Registar na lista para manter coerência
            users[username] = {"password": password, "role": "user"}
            save_users(users)
            
        if authenticated:
            session["user"] = username
            session["role"] = user_role
            return redirect(url_for("dashboard"))
            
        error = "Credenciais inválidas. Verifique o seu nome de utilizador e senha."
    return render_template("login.html", error=error)


@app.route("/access")
def access():
    """Rota direta para links de convite e credenciais temporárias com 1 clique."""
    token = request.args.get("token") or request.args.get("key")
    if not token:
        return redirect(url_for("login"))
    data = verify_access_token(token)
    if data and "user" in data:
        session["user"] = data["user"]
        session["role"] = data.get("role", "user")
        return redirect(url_for("dashboard"))
    return render_template("login.html", error="Este link de acesso temporário expirou ou é inválido.")


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


@app.route("/healthz")
def healthz():
    """Sonda de saúde usada para verificar o deploy."""
    return {
        "status": "ok",
        "docs_html": len(_doc_files()),
        "originals": len(_original_files()),
        "templates": TEMPLATES_DIR.is_dir(),
        "zip": ZIP_FILE.is_file(),
        "users_count": len(load_users()),
        "users_file": str(USERS_STORE),
        "path": request.path,
        "script_name": request.environ.get("SCRIPT_NAME", ""),
    }


@app.route("/dashboard")
def dashboard():
    if "user" not in session:
        return redirect(url_for("login"))
    doc_items = _get_doc_items()
    categories = {}
    for item in doc_items:
        categories.setdefault(item["category"], []).append(item)
    return render_template(
        "dashboard.html",
        user=session["user"],
        role=session.get("role", "user"),
        categories=categories,
        total_docs=len(doc_items),
    )


@app.route("/view/<path:identifier>")
def view_doc(identifier):
    if "user" not in session:
        return redirect(url_for("login"))
    doc_list = _doc_files()
    fpath = _resolve_target_file(DOCS_HTML_DIR, identifier, doc_list)
    content = fpath.read_text(encoding="utf-8", errors="ignore")
    return render_template(
        "viewer.html",
        filename=fpath.name,
        title=fpath.stem.replace("_", " "),
        content=content,
        user=session["user"],
    )


@app.route("/downloads", methods=["GET", "POST"])
def downloads():
    if "user" not in session:
        return redirect(url_for("login"))
    unlocked = session.get("download_unlocked", False)
    error = None
    if request.method == "POST":
        if (request.form.get("download_password") or "") == DOWNLOAD_PASSWORD:
            session["download_unlocked"] = True
            unlocked = True
        else:
            error = "Senha de download incorreta."
    
    orig_items = _get_original_items()
    categories = {}
    for item in orig_items:
        categories.setdefault(item["category"], []).append(item)

    return render_template(
        "downloads.html",
        unlocked=unlocked,
        categories=categories,
        total_originals=len(orig_items),
        error=error,
    )


@app.route("/download_file/<path:identifier>")
def download_file(identifier):
    if "user" not in session or not session.get("download_unlocked", False):
        return redirect(url_for("downloads"))
    orig_list = _original_files()
    fpath = _resolve_target_file(ORIGINALS_DIR, identifier, orig_list)
    return _file_response(fpath)


@app.route("/download_all")
def download_all():
    if "user" not in session or not session.get("download_unlocked", False):
        return redirect(url_for("downloads"))
    if not ZIP_FILE.is_file():
        abort(404)
    return _file_response(ZIP_FILE)


@app.route("/admin", methods=["GET", "POST"])
def admin():
    if "user" not in session or session.get("role") != "admin":
        return redirect(url_for("dashboard"))
        
    users = load_users()
    msg = None
    msg_type = "success"
    new_credentials = None
    
    if request.method == "POST":
        action = request.form.get("action", "create")
        
        if action == "delete":
            del_user = (request.form.get("delete_username") or "").strip()
            if del_user == "admin":
                msg = "Não é permitido eliminar o utilizador principal 'admin'."
                msg_type = "error"
            elif del_user in users:
                del users[del_user]
                save_users(users)
                msg = f"Utilizador '{del_user}' removido com sucesso."
                msg_type = "success"
            else:
                msg = f"Utilizador '{del_user}' não encontrado."
                msg_type = "error"
                
        else: # Criar ou atribuir credenciais
            new_user = (request.form.get("new_username") or "").strip()
            new_pass = (request.form.get("new_password") or "").strip()
            role = request.form.get("role", "user")
            
            if new_user:
                # Se não forneceu senha, gera senha temporária automática
                if not new_pass:
                    new_pass = generate_temp_password(new_user)
                    
                users[new_user] = {"password": new_pass, "role": role}
                if save_users(users):
                    token = generate_access_token(new_user, role)
                    base_url = request.host_url.rstrip("/")
                    access_url = f"{base_url}/access?token={token}"
                    new_credentials = {
                        "username": new_user,
                        "password": new_pass,
                        "role": role,
                        "access_url": access_url
                    }
                    msg = f"Credenciais para '{new_user}' atribuídas e ativadas com sucesso!"
                    msg_type = "success"
                else:
                    msg = "Não foi possível guardar o utilizador neste ambiente."
                    msg_type = "error"
            else:
                msg = "O nome de utilizador é obrigatório."
                msg_type = "error"
                
    # Preparar lista de utilizadores com tokens de acesso direto
    user_list = []
    base_url = request.host_url.rstrip("/")
    for uname, udata in users.items():
        token = generate_access_token(uname, udata.get("role", "user"))
        user_list.append({
            "username": uname,
            "password": udata.get("password", "—"),
            "role": udata.get("role", "user"),
            "access_url": f"{base_url}/access?token={token}"
        })
        
    return render_template(
        "admin.html",
        users=user_list,
        msg=msg,
        msg_type=msg_type,
        new_credentials=new_credentials,
    )


if __name__ == "__main__":
    app.run(
        host=os.environ.get("HOST", "0.0.0.0"),
        port=int(os.environ.get("PORT", 5000)),
        debug=False,
    )
