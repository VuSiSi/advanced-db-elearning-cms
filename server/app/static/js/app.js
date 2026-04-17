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
