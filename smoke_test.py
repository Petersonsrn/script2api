from app.core.config import settings
from app.services.converter import convert

r = convert("def add(a, b):\n    return a + b\n\ndef greet(name):\n    return f'Hello, {name}!'", "calc")
print("Config OK:", settings.app_name)
print("Endpoints found:", [e["path"] for e in r["endpoints"]])
print("Generated code preview:\n", r["generated_code"][:300])
