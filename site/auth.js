// ── AUTH COMPARTILHADO ────────────────────────────────────────────────────────
// HASH_PLACEHOLDER é substituído pelo CI (GitHub Secret AUTH_HASH)
const AUTH_HASH  = "AUTH_HASH";
const AUTH_LOCAL = AUTH_HASH === "HASH_PLACEHOLDER"; // dev local: sem auth

async function _sha256(str) {
  const buf = await crypto.subtle.digest("SHA-256", new TextEncoder().encode(str));
  return Array.from(new Uint8Array(buf)).map(b => b.toString(16).padStart(2, "0")).join("");
}

window.isAuth = function () {
  return AUTH_LOCAL || sessionStorage.getItem("rotas_auth") === AUTH_HASH;
};

function _applyHeaderAuthUI(authenticated) {
  const grp  = document.getElementById("header-auth");
  const icon = document.getElementById("header-auth-icon");
  const inp  = document.getElementById("header-auth-input");
  const btn  = document.getElementById("header-auth-btn");
  const msg  = document.getElementById("header-auth-msg");
  if (!grp) return;

  icon.textContent  = authenticated ? "🔓" : "🔒";
  inp.style.display = authenticated ? "none" : "";
  btn.style.display = authenticated ? "none" : "";
  if (msg) msg.textContent = "";

  let logoutBtn = document.getElementById("header-auth-logout");
  if (authenticated) {
    if (!logoutBtn) {
      logoutBtn = document.createElement("button");
      logoutBtn.id          = "header-auth-logout";
      logoutBtn.textContent = "Ocultar";
      logoutBtn.addEventListener("click", () => {
        sessionStorage.removeItem("rotas_auth");
        _applyHeaderAuthUI(false);
        window.dispatchEvent(new CustomEvent("authchange", { detail: { authenticated: false } }));
      });
      grp.appendChild(logoutBtn);
    }
    logoutBtn.style.display = "";
  } else {
    if (logoutBtn) logoutBtn.style.display = "none";
  }
}

function initHeaderAuth() {
  if (AUTH_LOCAL) {
    const grp = document.getElementById("header-auth");
    if (grp) grp.style.display = "none";
    // Dispatch after current call stack so page-JS listeners bind first
    setTimeout(() =>
      window.dispatchEvent(new CustomEvent("authchange", { detail: { authenticated: true } }))
    , 0);
    return;
  }

  // Make group visible now that JS is running (starts hidden in HTML to avoid flash)
  const grp = document.getElementById("header-auth");
  if (grp) grp.style.display = "";

  _applyHeaderAuthUI(window.isAuth());

  const btn = document.getElementById("header-auth-btn");
  const inp = document.getElementById("header-auth-input");
  const msg = document.getElementById("header-auth-msg");

  if (btn) btn.addEventListener("click", async () => {
    const hash = await _sha256(inp.value);
    if (hash !== AUTH_HASH) {
      if (msg) msg.textContent = "Senha incorreta";
      inp.value = "";
      return;
    }
    sessionStorage.setItem("rotas_auth", hash);
    _applyHeaderAuthUI(true);
    if (msg) msg.textContent = "";
    window.dispatchEvent(new CustomEvent("authchange", { detail: { authenticated: true } }));
  });

  if (inp) inp.addEventListener("keydown", e => {
    if (e.key === "Enter") btn.click();
  });
}

initHeaderAuth();
