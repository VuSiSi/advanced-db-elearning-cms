// ═══════════════════════════════════════════════════════════
//  TOKEN HELPERS  (must be defined first — used by everything below)
// ═══════════════════════════════════════════════════════════

function decodeJwtPayload(token) {
  const parts = String(token).split('.');
  if (parts.length < 2) return null;

  const base64Url = parts[1];
  const base64 = base64Url.replace(/-/g, '+').replace(/_/g, '/');
  const padded = base64 + '==='.slice((base64.length + 3) % 4);

  try {
    const binary = atob(padded);
    const bytes = Uint8Array.from(binary, (c) => c.charCodeAt(0));
    const json = new TextDecoder().decode(bytes);
    return JSON.parse(json);
  } catch {
    return null;
  }
}

function getUserRole() {
  const token = localStorage.getItem('token');
  if (!token) return null;
  const payload = decodeJwtPayload(token);
  return payload?.role || null;
}

/**
 * Returns true if there is no token OR the JWT exp has already passed.
 * Works purely on the client-side exp claim — no network call needed.
 */
function isTokenExpired() {
  const token = localStorage.getItem('token');
  if (!token) return true;

  const payload = decodeJwtPayload(token);
  if (!payload || typeof payload.exp !== 'number') return true;

  // exp is Unix time in seconds; Date.now() is ms
  return Date.now() >= payload.exp * 1000;
}

/**
 * Clear the stored token and bounce the user to /login.
 * Safe to call multiple times — guards against redirect loops.
 */
function handleExpiredSession() {
  localStorage.removeItem('token');
  if (window.location.pathname !== '/login') {
    window.location.replace('/login');
  }
}

function logout(e) {
  if (e) e.preventDefault();
  localStorage.removeItem('token');
  window.location.href = '/login';
}

function authHeaders() {
  const token = localStorage.getItem('token');
  return {
    'Content-Type': 'application/json',
    ...(token ? { 'Authorization': `Bearer ${token}` } : {}),
  };
}

/*
    LAYER 1 — Global fetch interceptor
      Catches any HTTP 401 returned by the backend (token expired or revoked server-side) and kicks the user to login.
*/
(function setupFetchInterceptor() {
  const _originalFetch = window.fetch;

  window.fetch = async function (...args) {
    const response = await _originalFetch.apply(this, args);

    if (response.status === 401) {
      // Do not read the body here — callers may still need it.
      // Redirect immediately; the in-flight page will be discarded.
      handleExpiredSession();
      
      return Promise.reject(new Error('Session expired'));
    }

    return response; // Always return so callers don't throw on undefined
  };
})();

// ═══════════════════════════════════════════════════════════
//  LAYER 2 — Page-load expiry check
//  Runs synchronously before the DOM is ready so protected
//  pages never render a single frame with a stale session.
// ═══════════════════════════════════════════════════════════
(function checkAuthAndRedirect() {
  const path = window.location.pathname;
  const token = localStorage.getItem('token');

  // If a token exists but its exp has passed → kick immediately
  if (token && isTokenExpired()) {
    handleExpiredSession();
    return;
  }

  // Root redirect logic
  if (path === '/') {
    if (!token) {
      window.location.replace('/login');
    } else {
      window.location.replace('/courses');
    }
  }

  // Force redirect for protected paths when not authenticated
  const protectedPaths = ['/courses/new', '/edit', '/analytics', '/my-progress'];
  if (!token && protectedPaths.some(p => path.includes(p))) {
    window.location.replace('/login');
  }
})();

// ═══════════════════════════════════════════════════════════
//  LAYER 3 — Periodic expiry poll
//  Checks every 30 seconds while the tab is open, so a user
//  who leaves a tab idle gets logged out without needing to
//  trigger an API call.
// ═══════════════════════════════════════════════════════════
(function startExpiryWatcher() {
  const INTERVAL_MS = 30_000; // 30 seconds

  setInterval(() => {
    // Skip watcher on the login page itself
    if (window.location.pathname === '/login') return;

    if (isTokenExpired()) {
      handleExpiredSession();
    }
  }, INTERVAL_MS);
})();

// ═══════════════════════════════════════════════════════════
//  NAVBAR
// ═══════════════════════════════════════════════════════════
document.addEventListener('DOMContentLoaded', initNavbar);

function initNavbar() {
  const navLinks = document.getElementById('nav-links');
  if (!navLinks) return;

  const role = getUserRole();

  if (!role) {
    navLinks.innerHTML = `
      <a href="/courses">Courses</a>
      <a href="/login">Login</a>
    `;
    return;
  }

  if (role === 'instructor') {
    const isCoursesPage = window.location.pathname === '/courses';
    const stressBtnHTML = isCoursesPage ? `
      <button class="btn-stress" onclick="openStressModal()" onmouseenter="startStressEffect(this)" onmouseleave="stopStressEffect(this)">
        <span class="stress-icon">⚠️</span>
        <span class="stress-text">sTrEsS tEsT</span>
        <span class="stress-icon">⚠️</span>
      </button>
    ` : '';

    navLinks.innerHTML = `
      ${stressBtnHTML}
      <a href="/courses">Courses</a>
      <a href="/courses/new">+ New Course</a>
      <a href="#" id="logout-btn">Logout</a>
    `;
  } else {
    navLinks.innerHTML = `
      <a href="/courses">Courses</a>
      <a href="#" id="logout-btn">Logout</a>
    `;
  }

  const btn = document.getElementById('logout-btn');
  if (btn) btn.addEventListener('click', logout);
}

// ═══════════════════════════════════════════════════════════
//  GLITCH EFFECT FOR STRESS TEST BUTTON
// ═══════════════════════════════════════════════════════════
let stressGlitchInterval = null;

function startStressEffect(btn) {
  const textEl = btn.querySelector('.stress-text');
  const baseText = "stress test";

  if (stressGlitchInterval) clearInterval(stressGlitchInterval);

  stressGlitchInterval = setInterval(() => {
    textEl.textContent = baseText.split('').map(char => {
      if (char === ' ') return ' ';
      return Math.random() > 0.5 ? char.toUpperCase() : char.toLowerCase();
    }).join('');
  }, 80);
}

function stopStressEffect(btn) {
  if (stressGlitchInterval) {
    clearInterval(stressGlitchInterval);
    stressGlitchInterval = null;
  }
  btn.querySelector('.stress-text').textContent = "sTrEsS tEsT";
}