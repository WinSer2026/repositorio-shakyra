"""Repositório Shakyra — aplicação Flask.

Funciona em execução local (`python app.py`) e no runtime Python da Vercel,
que deteta automaticamente o entrypoint `app.py` deste repositório.
"""

import json
import os
from pathlib import Path
from urllib.parse import quote

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

# Em ambientes serverless (Vercel) o código é montado em modo só-leitura e
# apenas /tmp permite escrita, onde ficam guardados os utilizadores criados
# no painel de administração.
TMP_DIR = Path(os.environ.get("TMPDIR") or "/tmp")
TMP_USERS_FILE = TMP_DIR / "shakyra_users.json"

# Acima deste tamanho a resposta é enviada em streaming, para não exceder o
# limite de 4,5 MB por resposta das Vercel Functions.
STREAM_THRESHOLD = 3 * 1024 * 1024
CHUNK_SIZE = 256 * 1024


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
    for path in (USERS_STORE, USERS_FILE):
        try:
            users = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if isinstance(users, dict) and users:
            return users
    return dict(DEFAULT_USERS)


def save_users(users):
    payload = json.dumps(users, indent=4, ensure_ascii=False)
    for path in (USERS_STORE, TMP_USERS_FILE):
        try:
            path.write_text(payload, encoding="utf-8")
            return True
        except OSError:
            continue
    return False


def _doc_files():
    return sorted(
        (f.name for f in DOCS_HTML_DIR.glob("*.html")),
        key=lambda name: name.casefold(),
    )


def _original_files():
    return sorted(
        (f.name for f in ORIGINALS_DIR.glob("*.*") if f.is_file() and not f.name.startswith("~$")),
        key=lambda name: name.casefold(),
    )


def _safe_file(directory, filename):
    """Impede acesso a ficheiros fora do diretório pretendido."""
    directory = directory.resolve()
    candidate = (directory / filename).resolve()
    if candidate.parent != directory or not candidate.is_file():
        abort(404)
    return candidate


def _content_disposition(filename):
    fallback = filename.encode("ascii", "ignore").decode("ascii").replace('"', "").strip()
    return 'attachment; filename="%s"; filename*=UTF-8\'\'%s' % (fallback or "download", quote(filename, safe=""))


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


app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "shakyra_secure_repository_secret_key_2026")


@app.route("/")
def index():
    if "user" not in session:
        return redirect(url_for("login"))
    return redirect(url_for("dashboard"))


@app.route("/login", methods=["GET", "POST"])
def login():
    error = None
    if request.method == "POST":
        username = (request.form.get("username") or "").strip()
        password = request.form.get("password") or ""
        users = load_users()
        account = users.get(username)
        if account and account.get("password") == password:
            session["user"] = username
            session["role"] = account.get("role", "user")
            return redirect(url_for("dashboard"))
        error = "Credenciais inválidas. Verifique o seu nome de utilizador e senha."
    return render_template("login.html", error=error)


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
        "users_file": str(USERS_STORE),
        "path": request.path,
        "script_name": request.environ.get("SCRIPT_NAME", ""),
    }


@app.route("/dashboard")
def dashboard():
    if "user" not in session:
        return redirect(url_for("login"))
    return render_template(
        "dashboard.html",
        user=session["user"],
        role=session.get("role", "user"),
        files=_doc_files(),
    )


@app.route("/view/<filename>")
def view_doc(filename):
    if "user" not in session:
        return redirect(url_for("login"))
    fpath = _safe_file(DOCS_HTML_DIR, filename)
    content = fpath.read_text(encoding="utf-8", errors="ignore")
    return render_template("viewer.html", filename=filename, content=content, user=session["user"])


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
    return render_template(
        "downloads.html",
        unlocked=unlocked,
        originals=_original_files(),
        error=error,
    )


@app.route("/download_file/<filename>")
def download_file(filename):
    if "user" not in session or not session.get("download_unlocked", False):
        return redirect(url_for("downloads"))
    fpath = _safe_file(ORIGINALS_DIR, filename)
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
    if request.method == "POST":
        new_user = (request.form.get("new_username") or "").strip()
        new_pass = request.form.get("new_password") or ""
        if new_user and new_pass:
            users[new_user] = {"password": new_pass, "role": "user"}
            if save_users(users):
                msg = "Utilizador '%s' criado com sucesso!" % new_user
            else:
                msg = "Não foi possível guardar o utilizador neste ambiente."
    return render_template("admin.html", users=users, msg=msg)


if __name__ == "__main__":
    app.run(
        host=os.environ.get("HOST", "0.0.0.0"),
        port=int(os.environ.get("PORT", 5000)),
        debug=False,
    )
