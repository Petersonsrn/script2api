import sys, asyncio
sys.path.insert(0, ".")

from app.db import init_db, create_user, get_user_by_email, count_uploads_this_month, log_upload
from app.services.auth import hash_password, verify_password, create_access_token, decode_token
from app.routers.auth import router as auth_router
from app.routers.convert import router as conv_router
print("[OK] Todos os imports ok")

# Testar hashing
h = hash_password("senha123")
assert verify_password("senha123", h)
assert not verify_password("errada", h)
print("[OK] bcrypt hash/verify ok")

# Testar JWT
tok = create_access_token("uuid-test", "a@b.com", "tester", "free")
payload = decode_token(tok)
assert payload["sub"] == "uuid-test"
assert payload["plan"] == "free"
print(f"[OK] JWT criado e decodificado: sub={payload['sub']}, plan={payload['plan']}")

# Testar DB completo
async def test_db():
    await init_db()
    print("[OK] DB init ok (arquivo script2api.db criado)")

    u = await create_user("test@example.com", "testuser", hash_password("pass123"))
    print(f"[OK] Usuario criado: id={u.id}, plan={u.plan}")

    found = await get_user_by_email("test@example.com")
    assert found is not None and found.username == "testuser"
    print("[OK] get_user_by_email ok")

    count_before = await count_uploads_this_month(u.id)
    assert count_before == 0
    print(f"[OK] count_uploads_this_month = {count_before} (esperado 0)")

    await log_upload(u.id, "test.py", "test", 3, "success", "")
    await log_upload(u.id, "test2.py", "test2", 1, "success", "")
    count_after = await count_uploads_this_month(u.id)
    assert count_after == 2
    print(f"[OK] Apos 2 uploads: count = {count_after}")

asyncio.run(test_db())

print()
print("Todos os testes passaram!")
