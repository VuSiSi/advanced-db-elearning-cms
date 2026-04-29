(function checkAuthAndRedirect() {
  const path = window.location.pathname;
  const token = localStorage.getItem('token');

  // If the user accesses the root directory localhost (/)
  if (path === '/') {
    if (!token) {
      // 
      window.location.replace('/login'); 
    } else {
      // 2. Has login session -> go to courses list page
      window.location.replace('/courses');
    }
  }

  // Additional security option: Force redirect to login if not logged in but trying to access sensitive pages
  const protectedPaths = ['/courses/new', '/edit', '/analytics', '/my-progress'];
  if (!token && protectedPaths.some(p => path.includes(p))) {
    window.location.replace('/login');
  }
})();

// ===== INIT NAVBAR =====
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
    navLinks.innerHTML = `
      <button class="btn-stress" onclick="openStressModal()" onmouseenter="startStressEffect(this)" onmouseleave="stopStressEffect(this)">        
        <span class="stress-icon">⚠️</span>
        <span class="stress-text">sTrEsS tEsT</span>
        <span class="stress-icon">⚠️</span>
      </button>
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

// ===== TOKEN HELPERS =====
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

// ── GLITCH EFFECT FOR STRESS TEST BUTTON ──
let stressGlitchInterval = null;

function startStressEffect(btn) {
  const textEl = btn.querySelector('.stress-text');
  const baseText = "stress test"; // Original text
  
  // Clear old interval if exists (avoid spam hover error)
  if (stressGlitchInterval) clearInterval(stressGlitchInterval);
  
  stressGlitchInterval = setInterval(() => {
    textEl.textContent = baseText.split('').map(char => {
      if (char === ' ') return ' '; // Keep space as is
      // 50-50 chance to flip upper/lower case for each letter
      return Math.random() > 0.5 ? char.toUpperCase() : char.toLowerCase();
    }).join('');
  }, 80); // 80ms: frame glitch speed
}

function stopStressEffect(btn) {
  if (stressGlitchInterval) {
    clearInterval(stressGlitchInterval);
    stressGlitchInterval = null;
  }
  // Return to default waiting state
  btn.querySelector('.stress-text').textContent = "sTrEsS tEsT";
}