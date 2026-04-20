// app.js — shared across all pages
// Handles: navbar auth state, token helpers

(function () {
  const token = localStorage.getItem('token');
  const navLinks = document.getElementById('nav-links');
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

  // "+ New Course" removed from navbar — course creation is now handled via
  // a modal on the courses page, keeping users in context.
  // Both roles share the same nav structure: Courses | Logout
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