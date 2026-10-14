# Repositório Shakyra

Repositório privado de documentos e relatórios do projeto de investigação
**Shakyra Honoré Kamdoum Noussi** (Universidade Técnica de Moçambique — Engenharia
e Gestão Logística): 81 relatórios em HTML para consulta protegida e 111 ficheiros
originais (DOCX/PDF/XLSX/PPTX) para download.

## Acesso

| Utilizador | Senha | Perfil |
| --- | --- | --- |
| `admin` | `admin_master_2026` | Administrador (pode criar utilizadores) |
| `user1` | `temp_user_pass_1` | Utilizador |

A senha do **Centro de Downloads** (área dos ficheiros originais) é
`download_secure_2026`.

> **Recomendado:** alterar estas credenciais. No painel `/admin` é possível criar
> novos utilizadores; as senhas vivem em `users.json`.

## Como funciona

Aplicação **Flask** (um único ficheiro, `app.py`):

| Rota | Descrição |
| --- | --- |
| `/login` | Autenticação (sessão em cookie assinado) |
| `/dashboard` | Índice dos relatórios em `docs_html/` |
| `/view/<ficheiro>` | Visualizador protegido (cópia/impressão bloqueadas + marca de água) |
| `/downloads` | Centro de downloads, protegido por senha |
| `/download_file/<ficheiro>` | Download individual de `originals/` |
| `/download_all` | Download do pacote `.zip` |
| `/admin` | Criação de utilizadores (só administradores) |
| `/healthz` | Sonda de saúde com diagnóstico do deploy |

## Executar localmente

```bash
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt
python app.py                    # http://localhost:5000
```

## Deploy (Vercel)

O projeto está ligado ao Vercel por Git: cada push para `master` gera um deploy
de produção. A configuração em `vercel.json` declara a função Python com o
entrypoint **na raiz**:

```json
{
  "version": 2,
  "builds": [{ "src": "app.py", "use": "@vercel/python" }],
  "routes": [{ "src": "/(.*)", "dest": "/app.py" }]
}
```

Detalhes importantes:

- **`requirements.txt` é obrigatório** — sem ele o Flask não é instalado no
  bundle da função e o site devolve `500 FUNCTION_INVOCATION_FAILED`.
- **O entrypoint tem de ficar na raiz.** O builder faz `glob('**')` a partir da
  pasta do entrypoint, pelo que `templates/`, `docs_html/`, `originals/`,
  `users.json` e `shakyra_completo.zip` só entram no bundle se o `app.py`
  estiver na raiz do repositório.
- **Sistema de ficheiros só-leitura.** Em produção só `/tmp` é gravável; os
  utilizadores criados no painel admin são guardados em
  `/tmp/shakyra_users.json` e podem desaparecer quando a instância é reciclada.
  Para credenciais persistentes, edite o `users.json` do repositório.
- **Downloads grandes.** Ficheiros acima de 3 MB (o `.zip` tem ~9 MB) são
  enviados em *streaming*, para não exceder o limite de 4,5 MB por resposta das
  Vercel Functions.
- Depois de cada deploy, confirmar em `/healthz` que `docs_html` = 81 e
  `originals` = 111.

## Estrutura

```
app.py                    aplicação Flask (entrypoint)
requirements.txt          dependências (Flask)
vercel.json               configuração da função na Vercel
templates/                templates Jinja (login, dashboard, viewer, downloads, admin)
docs_html/                relatórios HTML (visualização)
originals/                ficheiros originais para download
users.json                credenciais dos utilizadores
shakyra_completo.zip      pacote com todos os ficheiros originais
```
