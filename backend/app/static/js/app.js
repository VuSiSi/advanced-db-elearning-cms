// app.js — shared across all pages
// Handles: navbar auth state, token helpers

(function () {
  const token = localStorage.getItem('token');
  const navLinks = document.getElementById('nav-links');
  const path = window.location.pathname;
  if (!navLinks) return;

  // If not logged in, redirect to login page except when already on login page
  if (!token && path !== '/login') {
    window.location.href = '/login';
    return;
  }

  // If logged in, redirect to courses page
  if (token && path === '/login') {
    window.location.href = '/courses';
    return;
  }

  if (!navLinks) return;

  if (!token) {
    navLinks.innerHTML = `
      <a href="/courses">Courses</a>
      <a href="/login">Login</a>
    `;
    return;
  }

  // Decode JWT payload (no verification — server verifies on API calls)
  let role = '';
  try {
    const payload = JSON.parse(atob(token.split('.')[1]));
    role = payload.role || '';
  } catch {}

  navLinks.innerHTML = `
    <a href="/courses">Courses</a>
    <span style="color:var(--border-hover);margin:0 2px;user-select:none">|</span>
    <a href="#" onclick="logout()">Logout</a>
  `;
})();

function logout() {
  localStorage.removeItem('token');
  window.location.href = '/login';
}

// Helper used by all pages for authenticated API calls
function authHeaders() {
  const token = localStorage.getItem('token');
  return {
    'Content-Type': 'application/json',
    ...(token ? { 'Authorization': `Bearer ${token}` } : {}),
  };
}