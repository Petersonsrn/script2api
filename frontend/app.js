/* ============================================================
   Script2API — app.js
   Vanilla JS: upload, convert, execute, render results + Auth
   ============================================================ */

/**
 * API_BASE: lê da meta tag <meta name="api-url" content="...">
 * no index.html, ou do localStorage (dev override), ou fallback produção.
 *
 * Para apontar para um backend diferente localmente:
 *   localStorage.setItem("s2api_base", "http://localhost:8000")
 *   location.reload()
 */
const API_BASE = (() => {
  // 1. Override de desenvolvimento via localStorage
  const override = localStorage.getItem("s2api_base");
  if (override) return override.replace(/\/$/, "");
  // 2. Meta tag no HTML (configurado por ambiente no build)
  //    - content=""  → mesma origem (quando servido pelo backend)
  //    - content="https://..." → URL explícita
  const meta = document.querySelector('meta[name="api-url"]');
  if (meta && meta.content != null) {
    const url = meta.content.trim();
    if (url) return url.replace(/\/$/, "");
    return ""; // mesma origem
  }
  // 3. Fallback produção
  return "https://script2api.onrender.com";
})();

// Expõe para handlers onclick no HTML
window._apiBase = API_BASE;

// ── State ─────────────────────────────────────────────────
const state = {
  convert: { file: null },
  run:     { file: null },
  lastResult: null,
  pendingAction: null, // "convert" ou "run", salva o q ia fazer antes do login
};

// ============================================================
//   AUTH MANAGER
// ============================================================
const AuthManager = {
  getToken: () => localStorage.getItem("s2api_token"),
  setToken: (token) => localStorage.setItem("s2api_token", token),
  clearToken: () => localStorage.removeItem("s2api_token"),
  getHeaders: function() {
    const headers = {};
    const t = this.getToken();
    if(t) headers["Authorization"] = `Bearer ${t}`;
    return headers;
  },
  isLoggedIn: function() { return !!this.getToken(); },
  user: null
};

async function initAuth() {
  if(AuthManager.isLoggedIn()){
    try {
      const res = await fetch(`${API_BASE}/auth/me`, { headers: AuthManager.getHeaders() });
      if(res.ok) {
        AuthManager.user = await res.json();
        updateAuthUI(true);
      } else {
        AuthManager.clearToken();
        updateAuthUI(false);
      }
    } catch {
      updateAuthUI(false);
    }
  } else {
    updateAuthUI(false);
  }
}

function updateAuthUI(loggedIn) {
  const guestDiv = document.getElementById("header-guest");
  const userDiv  = document.getElementById("header-user");
  const heroUsg  = document.getElementById("usage-hero");

  if(loggedIn && AuthManager.user) {
    guestDiv.classList.add("hidden");
    userDiv.classList.remove("hidden");
    
    // UI
    document.getElementById("user-avatar").textContent = AuthManager.user.username.charAt(0).toUpperCase();
    document.getElementById("user-name-label").textContent = AuthManager.user.username;
    
    const badge = document.getElementById("plan-badge");
    badge.textContent = AuthManager.user.plan;
    badge.className = "plan-badge " + (AuthManager.user.plan === "pro" ? "pro" : "");

    // Hero usage
    if(AuthManager.user.usage && AuthManager.user.plan === "free") {
      heroUsg.classList.remove("hidden");
      const u = AuthManager.user.usage;
      document.getElementById("usage-hero-text").textContent = `${u.used} / ${u.limit} conversoes gratuitas no mes`;
      if(u.resets_on) document.getElementById("usage-hero-reset").textContent = `Reseta em ${u.resets_on}`;
      const pct = Math.min((u.used / u.limit) * 100, 100);
      const fill = document.getElementById("usage-hero-fill");
      fill.style.width = pct + "%";
      if(pct >= 100) fill.style.background = "var(--accent-red)";
      else if(pct >= 80) fill.style.background = "var(--accent-warn)";
      else fill.style.background = "var(--accent-green)";

      // Menu dropdown usage
      document.getElementById("menu-usage-text").textContent = `${u.used}/${u.limit}`;
      const mFill = document.getElementById("menu-usage-fill");
      mFill.style.width = pct + "%";
      if(pct >= 100) mFill.style.background = "var(--accent-red)";
      else if(pct >= 80) mFill.style.background = "var(--accent-warn)";
      else mFill.style.background = "var(--accent-green)";

      // Billing Buttons
      document.getElementById("btn-upgrade-pro").classList.remove("hidden");
      document.getElementById("btn-manage-sub").classList.add("hidden");
    } else {
      heroUsg.classList.add("hidden");
      document.getElementById("menu-usage-text").textContent = "∞ (Pro)";
      document.getElementById("menu-usage-fill").style.width = "100%";
      document.getElementById("menu-usage-fill").style.background = "var(--accent)";

      // Billing Buttons
      document.getElementById("btn-upgrade-pro").classList.add("hidden");
      document.getElementById("btn-manage-sub").classList.remove("hidden");
    }
  } else {
    guestDiv.classList.remove("hidden");
    userDiv.classList.add("hidden");
    heroUsg.classList.add("hidden");
  }
}

// ── Auth Modal ──────────────────────────────
function showAuthModal(tab = "login", pendingAction = null) {
  state.pendingAction = pendingAction;
  document.getElementById("auth-modal-overlay").classList.remove("hidden");
  switchAuthTab(tab);
}
function hideAuthModal() {
  document.getElementById("auth-modal-overlay").classList.add("hidden");
  state.pendingAction = null;
}
function closeAuthModal(e) {
  if(e.target.id === "auth-modal-overlay") hideAuthModal();
}
function switchAuthTab(tab) {
  document.getElementById("mtab-login").classList.toggle("active", tab === "login");
  document.getElementById("mtab-register").classList.toggle("active", tab === "register");
  document.getElementById("form-login").classList.toggle("hidden", tab !== "login");
  document.getElementById("form-register").classList.toggle("hidden", tab !== "register");
  document.getElementById("login-error").classList.add("hidden");
  document.getElementById("register-error").classList.add("hidden");
}

async function submitLogin(e) {
  e.preventDefault();
  const btn = document.getElementById("btn-login-submit");
  btn.disabled = true; btn.textContent = "Aguarde...";
  const errDiv = document.getElementById("login-error");
  errDiv.classList.add("hidden");

  try {
    const res = await fetch(`${API_BASE}/auth/login`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        email: document.getElementById("login-email").value,
        password: document.getElementById("login-password").value
      })
    });
    const data = await res.json();
    if(!res.ok) throw new Error(data.detail || "Erro no login");
    
    AuthManager.setToken(data.access_token);
    await initAuth();
    hideAuthModal();
    if(state.pendingAction === "convert") runConvert();
    if(state.pendingAction === "run") runExecute();
    if(state.pendingAction === "pro") checkoutPro();
  } catch(err) {
    errDiv.textContent = err.message;
    errDiv.classList.remove("hidden");
  } finally {
    btn.disabled = false; btn.innerHTML = '<span class="btn-icon">→</span> Entrar';
  }
}

async function submitRegister(e) {
  e.preventDefault();
  const btn = document.getElementById("btn-register-submit");
  btn.disabled = true; btn.textContent = "Criando conta...";
  const errDiv = document.getElementById("register-error");
  errDiv.classList.add("hidden");

  try {
    const res = await fetch(`${API_BASE}/auth/register`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        username: document.getElementById("reg-username").value,
        email: document.getElementById("reg-email").value,
        password: document.getElementById("reg-password").value
      })
    });
    const data = await res.json();
    if(!res.ok) {
      if(Array.isArray(data.detail)) throw new Error(data.detail[0].msg);
      throw new Error(data.detail || "Erro no cadastro");
    }
    
    AuthManager.setToken(data.access_token);
    await initAuth();
    hideAuthModal();
    if(state.pendingAction === "convert") runConvert();
    if(state.pendingAction === "run") runExecute();
    if(state.pendingAction === "pro") checkoutPro();
  } catch(err) {
    errDiv.textContent = err.message;
    errDiv.classList.remove("hidden");
  } finally {
    btn.disabled = false; btn.innerHTML = '<span class="btn-icon">✓</span> Criar conta grátis';
  }
}

function selectUserMenu() {} // dummy
function toggleUserMenu() {
  document.getElementById("user-menu").classList.toggle("hidden");
}
window.addEventListener("click", e => {
  if(!e.target.closest("#header-user")) {
    document.getElementById("user-menu")?.classList.add("hidden");
  }
});
function logout() {
  AuthManager.clearToken();
  AuthManager.user = null;
  updateAuthUI(false);
  showToast("Desconectado com sucesso", "info");
}

// ── HIstory Panel ──────────────────────────
async function openHistory() {
  document.getElementById("user-menu").classList.add("hidden");
  document.getElementById("history-overlay").classList.remove("hidden");
  const list = document.getElementById("history-list");
  list.innerHTML = '<div class="history-loading">Carregando histórico...</div>';

  if(!AuthManager.isLoggedIn()) return;
  
  try {
    const res = await fetch(`${API_BASE}/auth/history`, { headers: AuthManager.getHeaders() });
    if(!res.ok) throw new Error("Erro ao carregar");
    const data = await res.json();
    
    if(!data.items || data.items.length === 0) {
      list.innerHTML = '<div class="history-loading">Nenhum histórico encontrado.</div>';
      return;
    }

    list.innerHTML = "";
    data.items.forEach(item => {
      const cls = item.status === "success" ? "success" : "error";
      const d = new Date(item.created_at).toLocaleString("pt-BR", {
        day: '2-digit', month: '2-digit', year: '2-digit', hour: '2-digit', minute: '2-digit'
      });
      const endpointsInfo = item.endpoints > 0 ? `(${item.endpoints} endpoints)` : '';
      let errHTML = "";
      if(item.error) errHTML = `<div class="history-item-error">${item.error}</div>`;

      list.innerHTML += `
        <div class="history-item">
          <div class="history-item-top">
            <div>
              <div class="history-item-file">${item.filename}</div>
              ${item.script_name ? `<div class="history-item-func">${item.script_name} ${endpointsInfo}</div>` : ''}
            </div>
            <span class="history-item-status ${cls}">${item.status}</span>
          </div>
          ${errHTML}
          <div class="history-item-date">
            <span>ID: ${item.id.substring(0,8)}</span>
            <span>${d}</span>
          </div>
        </div>
      `;
    });
  } catch(err) {
    list.innerHTML = `<div class="history-loading" style="color:var(--accent-red)">${err.message}</div>`;
  }
}
function closeHistoryPanel() {
  document.getElementById("history-overlay").classList.add("hidden");
}
function closeHistory(e) {
  if(e.target.id === "history-overlay") closeHistoryPanel();
}


// ============================================================
//   MAIN APP LOGIC
// ============================================================

document.addEventListener("DOMContentLoaded", async () => {
  await initAuth();
  
  // Handlers for stripe checkout redirects
  const params = new URLSearchParams(window.location.search);
  if(params.get("success") === "true") {
    showToast("Assinatura confirmada com sucesso! Bem-vindo ao Pro.", "success");
    window.history.replaceState({}, document.title, window.location.pathname);
  }
  if(params.get("canceled") === "true") {
    showToast("Assinatura cancelada.", "error");
    window.history.replaceState({}, document.title, window.location.pathname);
  }

  // Handlers for landing page actions
  if(params.get("action") === "register") {
    if (!AuthManager.isLoggedIn()) {
      showAuthModal("register");
    }
  }
  if(params.get("action") === "pro") {
    if (!AuthManager.isLoggedIn()) {
      showToast("Crie sua conta ou faça login para assinar o plano Pro", "info");
      showAuthModal("register", "pro");
    } else {
      checkoutPro();
    }
  }
});

// ── Tab switching ──────────────────────────────────────────
function switchTab(name) {
  document.querySelectorAll(".tab").forEach(t => {
    t.classList.toggle("active", t.id === `tab-${name}`);
  });
  document.querySelectorAll(".panel").forEach(p => {
    p.classList.toggle("active", p.id === `panel-${name}`);
  });
  hideResult();
}

// ── Drag & Drop ────────────────────────────────────────────
function onDragOver(e) { e.preventDefault(); e.currentTarget.classList.add("drag-over"); }
function onDragLeave(e) { e.currentTarget.classList.remove("drag-over"); }
function onDrop(e, ctx) {
  e.preventDefault(); e.currentTarget.classList.remove("drag-over");
  const file = e.dataTransfer.files[0];
  if (file) applyFile(file, ctx);
}
function onFileSelect(e, ctx) {
  const file = e.target.files[0];
  if (file) applyFile(file, ctx);
}

function applyFile(file, ctx) {
  if (!file.name.endsWith(".py")) {
    showToast("⚠ Apenas arquivos .py sao aceitos", "error");
    return;
  }
  state[ctx].file = file;
  document.getElementById(`file-badge-name-${ctx}`).textContent = file.name;
  document.getElementById(`file-badge-${ctx}`).classList.remove("hidden");
  const zone = ctx === "convert" ? document.getElementById("upload-zone") : document.getElementById("upload-zone-run");
  zone.classList.add("has-file");
  document.getElementById(ctx === "convert" ? "btn-convert" : "btn-run").disabled = false;
  hideResult();
}

function clearFile(ctx) {
  state[ctx].file = null;
  document.getElementById(`file-badge-${ctx}`).classList.add("hidden");
  document.getElementById(`file-${ctx}`).value = "";
  const zone = ctx === "convert" ? document.getElementById("upload-zone") : document.getElementById("upload-zone-run");
  zone.classList.remove("has-file");
  document.getElementById(ctx === "convert" ? "btn-convert" : "btn-run").disabled = true;
  hideResult();
}

// ── Loading & Toast ────────────────────────────────────────
function showLoading(msg = "Processando...") {
  document.getElementById("loading-text").textContent = msg;
  document.getElementById("loading-overlay").classList.remove("hidden");
}
function hideLoading() {
  document.getElementById("loading-overlay").classList.add("hidden");
}
function showToast(msg, type = "info") {
  const t = document.createElement("div");
  t.textContent = msg;
  t.style.cssText = `
    position:fixed; bottom:24px; right:24px; z-index:9999;
    background:${type === "error" ? "rgba(244,63,94,0.9)" : "rgba(34,197,94,0.9)"};
    color:#fff; padding:12px 20px; border-radius:10px;
    font-size:.88rem; font-family:'Inter',sans-serif;
    box-shadow:0 4px 20px rgba(0,0,0,.4);
    animation: slideIn .25s ease;
  `;
  document.body.appendChild(t);
  setTimeout(() => t.remove(), 3000);
}

// ── CONVERT ────────────────────────────────────────────────
async function runConvert() {
  if(!AuthManager.isLoggedIn()) {
    showAuthModal("login", "convert");
    return;
  }
  const file = state.convert.file;
  if (!file) return;

  const formData = new FormData();
  formData.append("file", file);

  showLoading("Convertendo script...");
  hideResult();

  try {
    const res = await fetch(`${API_BASE}/convert/upload`, {
      method: "POST",
      headers: AuthManager.getHeaders(),
      body: formData,
    });
    const data = await res.json();
    if (!res.ok) {
      if(res.status === 429 && data.detail && data.detail.message) {
        renderError(data.detail.message, res.status);
      } else {
        renderError(data.detail || "Erro ao converter", res.status);
      }
      initAuth(); // refresh usage
    } else {
      renderConvertResult(data);
      initAuth(); // refresh limit header
    }
  } catch (err) {
    renderError(`Nao foi possivel conectar ao servidor.\nErro: ${err.message}`, 0);
  } finally {
    hideLoading();
  }
}

// ── EXECUTE ────────────────────────────────────────────────
async function runExecute() {
  if(!AuthManager.isLoggedIn()) {
    showAuthModal("login", "run");
    return;
  }
  const file = state.run.file;
  if (!file) return;

  const funcName = document.getElementById("func-name").value.trim();
  if (!funcName) {
    showToast("⚠ Informe o nome da funcao", "error");
    document.getElementById("func-name").focus();
    return;
  }

  let args = "{}";
  try {
    const raw = document.getElementById("func-args").value.trim() || "{}";
    const p = JSON.parse(raw);
    if (typeof p !== "object" || Array.isArray(p)) throw new Error();
    args = JSON.stringify(p);
  } catch {
    showToast("⚠ Argumentos inalidos — use JSON object: {\"a\": 1}", "error");
    return;
  }

  const timeout = parseFloat(document.getElementById("timeout").value) || 5;
  const formData = new FormData();
  formData.append("file", file);
  formData.append("func_name", funcName);
  formData.append("args", args);
  formData.append("timeout", timeout);

  showLoading(`Executando ${funcName}()...`);
  hideResult();

  try {
    const res = await fetch(`${API_BASE}/convert/upload-and-run`, {
      method: "POST",
      headers: AuthManager.getHeaders(),
      body: formData,
    });
    const data = await res.json();
    if (!res.ok) {
      if(res.status === 429 && data.detail && data.detail.message) {
        renderError(data.detail.message, res.status);
      } else {
        renderError(data.detail || "Erro ao executar", res.status);
      }
      initAuth(); // refresh usage
    } else {
      renderRunResult(data);
      initAuth(); // refresh limit header
    }
  } catch (err) {
    renderError(`Nao foi possivel conectar ao servidor.\nErro: ${err.message}`, 0);
  } finally {
    hideLoading();
  }
}

// ── RENDER ────────────────────────────────────────────────
function renderConvertResult(data) {
  state.lastResult = data;
  showResultBlock();
  const success = data.success && data.endpoints?.length > 0;
  setStatus(success, success ? `${data.endpoints.length} endpoint(s) gerado(s)` : (data.warnings?.[0] || "Erro"), null);

  if (data.warnings?.length) {
    showSection("error-section");
    const box = document.getElementById("error-box");
    box.textContent = "⚠ " + data.warnings.join("\n⚠ ");
    box.style.background = "rgba(245,158,11,0.08)";
    box.style.borderColor = "rgba(245,158,11,0.25)";
    box.style.color = "#fcd34d";
  }

  if (data.endpoints?.length) {
    showSection("endpoints-section");
    const list = document.getElementById("endpoints-list");
    list.innerHTML = "";
    data.endpoints.forEach(ep => {
      list.innerHTML += `<div class="endpoint-card">
        <span class="endpoint-method">${ep.method}</span>
        <span class="endpoint-path">${ep.path}</span>
        <span class="endpoint-args">${ep.args?.length ? ep.args.join(", ") : "no args"}</span>
      </div>`;
    });
  }

  if (data.generated_code) {
    showSection("code-section");
    document.getElementById("generated-code").textContent = data.generated_code;
  }
  renderUsage(data.usage);
}

function renderRunResult(data) {
  state.lastResult = data;
  showResultBlock();
  setStatus(data.success, data.success ? `${data.func_name}() executado com sucesso` : `Erro em ${data.func_name}()`, data.exec_time_ms ? `${data.exec_time_ms.toFixed(2)}ms` : null);

  if (data.success) {
    showSection("exec-section");
    const formatted = typeof data.result === "object" ? JSON.stringify(data.result, null, 2) : String(data.result);
    document.getElementById("exec-result").textContent = formatted;
  } else if (data.error) {
    showSection("error-section");
    const box = document.getElementById("error-box");
    box.style.cssText = ""; box.textContent = data.error;
  }
  renderUsage(data.usage);
}

function renderError(msg, status) {
  state.lastResult = { error: msg };
  showResultBlock();
  setStatus(false, status ? `HTTP ${status} — Erro` : "Falha de conexao", null);
  showSection("error-section");
  const box = document.getElementById("error-box");
  box.style.cssText = ""; box.textContent = msg;
}

// ── HELPERS ────────────────────────────────────────────────
function showResultBlock() {
  document.getElementById("result-separator").classList.remove("hidden");
  document.getElementById("result-block").classList.remove("hidden");
  ["endpoints-section","code-section","exec-section","error-section","usage-result"].forEach(id => {
    document.getElementById(id).classList.add("hidden");
  });
}
function hideResult() {
  document.getElementById("result-separator").classList.add("hidden");
  document.getElementById("result-block").classList.add("hidden");
}
function setStatus(success, text, execTime) {
  document.getElementById("result-status-dot").className = "result-status-dot " + (success ? "success" : "error");
  document.getElementById("result-status-text").textContent = text;
  document.getElementById("result-exec-time").textContent = execTime ? `⏱ ${execTime}` : "";
}
function showSection(id) { document.getElementById(id).classList.remove("hidden"); }

function renderUsage(usage) {
  if (!usage) return;
  showSection("usage-result");
  const plan = usage.plan;
  document.getElementById("usage-result-plan").textContent = plan;
  if(plan === "free") {
    document.getElementById("usage-result-label").textContent = `${usage.used}/${usage.limit} usos`;
    const pct = Math.min((usage.used / usage.limit) * 100, 100);
    const fill = document.getElementById("usage-bar-fill");
    fill.style.width = pct + "%";
    if(pct >= 100) fill.style.background = "var(--accent-red)";
    else if(pct >= 80) fill.style.background = "var(--accent-warn)";
    else fill.style.background = "var(--accent-green)";
  } else {
    document.getElementById("usage-result-label").textContent = `Ilimitado`;
    document.getElementById("usage-bar-fill").style.width = "100%";
    document.getElementById("usage-bar-fill").style.background = "var(--accent)";
  }
}

// ── BILLING ──────────────────────────────────────────────────
async function checkoutPro() {
  const btn = document.getElementById("btn-upgrade-pro");
  btn.textContent = "Aguarde..."; btn.disabled = true;
  try {
    const res = await fetch(`${API_BASE}/billing/create-checkout-session`, {
      method: "POST", headers: AuthManager.getHeaders()
    });
    const data = await res.json();
    if(!res.ok) throw new Error(data.detail || "Erro");
    window.location.href = data.url;
  } catch(err) {
    showToast(err.message, "error");
    btn.textContent = "🌟 Upgrade para Pro"; btn.disabled = false;
  }
}

async function manageSubscription() {
  const btn = document.getElementById("btn-manage-sub");
  btn.textContent = "Aguarde..."; btn.disabled = true;
  try {
    const res = await fetch(`${API_BASE}/billing/create-portal-session`, {
      method: "POST", headers: AuthManager.getHeaders()
    });
    const data = await res.json();
    if(!res.ok) throw new Error(data.detail || "Erro");
    window.location.href = data.url;
  } catch(err) {
    showToast(err.message, "error");
    btn.textContent = "💳 Gerenciar Assinatura"; btn.disabled = false;
  }
}

// ── COPY ──────────────────────────────────────────────────
function copyResult() {
  const text = JSON.stringify(state.lastResult, null, 2);
  navigator.clipboard.writeText(text).then(() => {
    const btn = document.getElementById("btn-copy");
    btn.textContent = "✓ Copiado!"; btn.classList.add("copied");
    setTimeout(() => { btn.textContent = "📋 Copiar"; btn.classList.remove("copied"); }, 2000);
  });
}
function copyCode() {
  const code = document.getElementById("generated-code").textContent;
  navigator.clipboard.writeText(code).then(() => showToast("✓ Codigo copiado!", "success"));
}
