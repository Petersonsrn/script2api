# test_sandbox_local.py — Testes do motor de execucao segura.
# Execute de dentro da pasta script2api com: python test_sandbox_local.py
import sys
sys.path.insert(0, ".")

from app.services.sandbox import execute_function, SecurityError, audit_ast

PASS = "\033[92m[OK]\033[0m"
FAIL = "\033[91m[FAIL]\033[0m"

errors = []

def check(label, condition, detail=""):
    if condition:
        print(f"  {PASS} {label}")
    else:
        print(f"  {FAIL} {label} — {detail}")
        errors.append(label)

print("\n=== Testes do Sandbox ===\n")

# ── T1: Função simples
r = execute_function("def soma(a, b): return a + b", "soma", {"a": 3, "b": 7})
check("soma(3,7) == 10", r["success"] and r["result"] == 10, r)

# ── T2: String
r = execute_function("def greet(name): return 'Ola ' + name", "greet", {"name": "Mondo"})
check("greet retorna string", r["success"] and r["result"] == "Ola Mondo", r)

# ── T3: import os bloqueado
r = execute_function("import os\ndef fn(): return os.getcwd()", "fn", {})
check("import os bloqueado", not r["success"] and "SecurityError" in r["error"], r)

# ── T4: exec() bloqueado (deve ser barrado na auditoria AST)
src_exec = 'def fn():\n    exec("x=1")\n    return x'
r = execute_function(src_exec, "fn", {})
check("exec() bloqueado por AST", not r["success"] and "SecurityError" in r["error"], r)

# ── T5: eval() bloqueado
src_eval = 'def fn(x): return eval(x)'
r = execute_function(src_eval, "fn", {"x": "1+1"})
check("eval() bloqueado por AST", not r["success"] and "SecurityError" in r["error"], r)

# ── T6: open() bloqueado em runtime (não está nos builtins)
src_open = 'def fn(): return open("test.txt").read()'
r = execute_function(src_open, "fn", {})
check("open() bloqueado em runtime", not r["success"], r)

# ── T7: import subprocess bloqueado
src_sub = "import subprocess\ndef fn(): return subprocess.check_output('dir')"
r = execute_function(src_sub, "fn", {})
check("import subprocess bloqueado", not r["success"] and "SecurityError" in r["error"], r)

# ── T8: função não encontrada
r = execute_function("def soma(a, b): return a + b", "inexistente", {})
check("funcao inexistente retorna erro claro", not r["success"] and "inexistente" in r["error"], r)

# ── T9: Erro de sintaxe no script
r = execute_function("def fn(: return 1", "fn", {})
check("syntax error retorna erro", not r["success"], r)

# ── T10: Resultado com lista
r = execute_function("def fn(): return [1, 2, 3]", "fn", {})
check("resultado lista JSON-serializável", r["success"] and r["result"] == [1, 2, 3], r)

# ── T11: Resultado com dict
r = execute_function("def fn(x): return {'dobro': x * 2}", "fn", {"x": 21})
check("resultado dict JSON-serializável", r["success"] and r["result"] == {"dobro": 42}, r)

# ── T12: Timeout (import time é bloqueado, mas testamos com argumento ruim)
r = execute_function("def fn(n): return sum(range(n))", "fn", {"n": 10_000_000})
check("funcao pesada executa (dentro do tempo)", r["success"], r)

print()
if errors:
    print(f"\033[91m{len(errors)} teste(s) falharam:\033[0m {errors}")
    sys.exit(1)
else:
    print(f"\033[92mTodos os {12} testes passaram!\033[0m\n")
