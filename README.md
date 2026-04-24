<div align="center">

# 🐍→⚡ Script2API

[![Python](https://img.shields.io/badge/python-3.10+-blue?style=for-the-badge&logo=python)](https://python.org)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.111-009688?style=for-the-badge&logo=fastapi)](https://fastapi.tiangolo.com)
[![License](https://img.shields.io/badge/license-MIT-7C3AED?style=for-the-badge)](LICENSE)

**Turn any Python script into a production-ready REST API in seconds.**

[📖 Docs](http://localhost:8000/docs) · [🐛 Issues](https://github.com/your-username/script2api/issues) · [⭐ Star on GitHub](https://github.com/your-username/script2api)

</div>

---

## 🎯 What is Script2API?

Script2API reads your Python source code, discovers every public top-level function using the `ast` module, and automatically wraps each one in a **FastAPI POST endpoint** — with type hints, Pydantic request models and Swagger docs included.

**Before** (your script):
```python
def add(a, b):
    """Adds two numbers."""
    return a + b

def greet(name):
    return f"Hello, {name}!"
```

**After** (generated API — `POST /script/add` and `POST /script/greet`):
```json
POST /script/add
{
  "a": 3,
  "b": 5
}
→ { "result": 8 }
```

---

## 📁 Project Structure

```
script2api/
├── main.py                   ← App entrypoint + factory
├── requirements.txt
├── .env.example
├── docker-compose.yml        ← Local dev stack (app + PostgreSQL)
└── app/
    ├── core/
    │   └── config.py         ← Settings loaded from .env
    ├── routers/
    │   ├── auth.py           ← POST /auth/register, /auth/login
    │   ├── billing.py        ← Stripe checkout, portal & webhooks
    │   ├── convert.py        ← POST /convert  (JSON + file upload)
    │   └── health.py         ← GET  /health
    └── services/
        ├── auth.py           ← JWT + bcrypt helpers
        ├── converter.py      ← AST parser + code generator
        ├── sandbox.py        ← Restricted code execution
        └── usage.py          ← Rate-limit logic (shared)
```

---

## 🚀 Running Locally

### 1. Clone & install
```bash
git clone https://github.com/your-username/script2api.git
cd script2api

pip install -r requirements.txt
```

### 2. Configure environment
```bash
cp .env.example .env
# Edit .env if needed (defaults work fine for local dev)
```

### 3. Start with helper script (recommended)
```bash
# Aguarda PostgreSQL, roda migrations e sobe o servidor
python scripts/start.py

# Modo produção (sem reload)
python scripts/start.py --production
```

### 3-alt. Start with Docker Compose
```bash
docker-compose up -d
# Cria as tabelas via Alembic
alembic upgrade head
```

### 3-alt. Start manually (needs local PostgreSQL)
```bash
# Crie as tabelas (ou rode alembic upgrade head)
uvicorn main:app --reload --port 8000
```

### 4. Migrations (Alembic)
```bash
# Criar nova migration
alembic revision -m "descrição"

# Aplicar migrations
alembic upgrade head

# Reverter uma migration
alembic downgrade -1
```

### 5. Open the docs
Visit → **http://localhost:8000/docs**

---

## 🌐 API Reference

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/` | Service info |
| `GET` | `/health` | Health check |
| `POST` | `/convert` | Convert Python source (JSON body) |
| `POST` | `/convert/upload` | Upload a `.py` file directly |
| `GET` | `/convert/usage` | Check usage quota (authenticated) |
| `POST` | `/convert/run` | Execute a function inline |
| `POST` | `/convert/upload-and-run` | Upload `.py` and run a function |
| `POST` | `/auth/register` | Create account |
| `POST` | `/auth/login` | Login (returns JWT) |
| `GET` | `/auth/me` | Current user + usage |
| `GET` | `/auth/history` | Upload/conversion history (paginated) |
| `DELETE` | `/auth/me` | Delete account and all data (LGPD/GDPR) |
| `POST` | `/billing/create-checkout-session` | Start Pro subscription |
| `POST` | `/billing/create-portal-session` | Manage subscription |
| `POST` | `/billing/webhook` | Stripe events (idempotent) |

### Example request
```bash
curl -X POST http://localhost:8000/convert \
  -H "Content-Type: application/json" \
  -d '{
    "source": "def double(n):\n    return n * 2",
    "script_name": "math_utils"
  }'
```

---

## 💰 Monetization Model

| Tier | Conversions/month | File Upload | API Access | Price |
|------|:-----------------:|:-----------:|:----------:|-------|
| Free | 10 | ✅ | ❌ | $0 |
| Pro | Unlimited | ✅ | ✅ | $9/mo |

---

## 🗺️ Roadmap

- [x] AST-based function extraction
- [x] Auto Pydantic model generation
- [x] File upload support
- [x] Free / Pro usage tracking
- [x] Persistent storage (PostgreSQL)
- [x] Stripe payment integration
- [ ] GitHub OAuth login
- [ ] Generated API deployment (run on cloud, not just generate code)
- [ ] GitHub Action for CI/CD integration

---

## 📄 License

MIT — feel free to use, fork and build on top of it.

---

<div align="center">Made with ❤️ — ⭐ Star us if this saves you time!</div>
