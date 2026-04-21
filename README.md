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
└── app/
    ├── core/
    │   └── config.py         ← Settings loaded from .env
    ├── routers/
    │   ├── convert.py        ← POST /convert  (JSON + file upload)
    │   └── health.py         ← GET  /health
    └── services/
        └── converter.py      ← AST parser + code generator
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

### 3. Start the server
```bash
uvicorn main:app --reload --port 8000
```

### 4. Open the docs
Visit → **http://localhost:8000/docs**

---

## 🌐 API Reference

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/` | Service info |
| `GET` | `/health` | Health check |
| `POST` | `/convert` | Convert Python source (JSON body) |
| `POST` | `/convert/upload` | Upload a `.py` file directly |
| `GET` | `/convert/usage/{user_id}` | Check usage quota |

### Example request
```bash
curl -X POST http://localhost:8000/convert \
  -H "Content-Type: application/json" \
  -d '{
    "source": "def double(n):\n    return n * 2",
    "script_name": "math_utils",
    "user_id": "user_123"
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
- [ ] Persistent storage (SQLite → PostgreSQL)
- [ ] GitHub OAuth login
- [ ] Stripe payment integration
- [ ] Generated API deployment (run on cloud, not just generate code)
- [ ] GitHub Action for CI/CD integration

---

## 📄 License

MIT — feel free to use, fork and build on top of it.

---

<div align="center">Made with ❤️ — ⭐ Star us if this saves you time!</div>
