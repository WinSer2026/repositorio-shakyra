from flask import Flask, render_template, request, redirect, url_for, session, send_file, abort
import json
from pathlib import Path
import zipfile

app = Flask(__name__)
app.secret_key = "shakyra_secure_repository_secret_key_2026"

REPO_DIR = Path(r"C:\Users\USER\Documents\shakyra\Repositorio_Shakyra")
DOCS_HTML_DIR = REPO_DIR / "docs_html"
ORIGINALS_DIR = REPO_DIR / "originals"
USERS_FILE = REPO_DIR / "users.json"

if not USERS_FILE.exists():
    default_users = {
        "admin": {"password": "admin_master_2026", "role": "admin"},
        "user1": {"password": "temp_user_pass_1", "role": "user"}
    }
    USERS_FILE.write_text(json.dumps(default_users, indent=4), encoding='utf-8')

def load_users():
    return json.loads(USERS_FILE.read_text(encoding='utf-8'))

def save_users(users):
    USERS_FILE.write_text(json.dumps(users, indent=4), encoding='utf-8')

@app.route("/")
def index():
    if "user" not in session:
        return redirect(url_for("login"))
    return redirect(url_for("dashboard"))

@app.route("/login", methods=["GET", "POST"])
def login():
    error = None
    if request.method == "POST":
        username = request.form.get("username")
        password = request.form.get("password")
        users = load_users()
        if username in users and users[username]["password"] == password:
            session["user"] = username
            session["role"] = users[username]["role"]
            return redirect(url_for("dashboard"))
        else:
            error = "Credenciais inválidas. Verifique o seu nome de utilizador e senha."
    return render_template("login.html", error=error)

@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))

@app.route("/dashboard")
def dashboard():
    if "user" not in session:
        return redirect(url_for("login"))
    html_files = [f.name for f in DOCS_HTML_DIR.glob("*.html")]
    return render_template("dashboard.html", user=session["user"], role=session["role"], files=html_files)

@app.route("/view/<filename>")
def view_doc(filename):
    if "user" not in session:
        return redirect(url_for("login"))
    fpath = DOCS_HTML_DIR / filename
    if not fpath.exists():
        abort(404)
    content = fpath.read_text(encoding='utf-8', errors='ignore')
    return render_template("viewer.html", filename=filename, content=content, user=session["user"])

@app.route("/downloads", methods=["GET", "POST"])
def downloads():
    if "user" not in session:
        return redirect(url_for("login"))
    unlocked = session.get("download_unlocked", False)
    error = None
    if request.method == "POST":
        dl_pass = request.form.get("download_password")
        if dl_pass == "download_secure_2026":
            session["download_unlocked"] = True
            unlocked = True
        else:
            error = "Senha de download incorreta."
    originals = [f.name for f in ORIGINALS_DIR.glob("*.*")]
    return render_template("downloads.html", unlocked=unlocked, originals=originals, error=error)

@app.route("/download_file/<filename>")
def download_file(filename):
    if "user" not in session or not session.get("download_unlocked", False):
        return redirect(url_for("downloads"))
    fpath = ORIGINALS_DIR / filename
    if not fpath.exists():
        abort(404)
    return send_file(fpath, as_attachment=True)

@app.route("/download_all")
def download_all():
    if "user" not in session or not session.get("download_unlocked", False):
        return redirect(url_for("downloads"))
    zip_path = REPO_DIR / "shakyra_completo.zip"
    if not zip_path.exists():
        abort(404)
    return send_file(zip_path, as_attachment=True)

@app.route("/admin", methods=["GET", "POST"])
def admin():
    if "user" not in session or session.get("role") != "admin":
        return redirect(url_for("dashboard"))
    users = load_users()
    msg = None
    if request.method == "POST":
        new_user = request.form.get("new_username")
        new_pass = request.form.get("new_password")
        if new_user and new_pass:
            users[new_user] = {"password": new_pass, "role": "user"}
            save_users(users)
            msg = f"Utilizador '{new_user}' criado com sucesso!"
    return render_template("admin.html", users=users, msg=msg)

if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5000, debug=False)
