// app.js — shared across all pages
// Handles: navbar auth state, token helpers, role-aware page routing

function getToken() {
  return localStorage.getItem('token');
}

function getTokenPayload() {
  const token = getToken();
  if (!token) return null;
  try {
    return JSON.parse(atob(token.split('.')[1]));
  } catch {
    return null;
  }
}

function getCurrentUserRole() {
  return getTokenPayload()?.role || '';
}

function getCurrentUserId() {
  return getTokenPayload()?.sub || '';
}

function getInstructorCourseUrl(courseId) {
  return `/courses/${courseId}`;
}

function getStudentCourseUrl(courseId) {
  return `/courses/${courseId}/learn`;
}

function getDefaultCourseUrl(courseId) {
  return getCurrentUserRole() === 'student'
    ? getStudentCourseUrl(courseId)
    : getInstructorCourseUrl(courseId);
}

(function () {
  const token = getToken();
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

  const role = getCurrentUserRole();
  const roleChip = role
    ? `<span style="font-size:12px;color:var(--text-muted);text-transform:capitalize">${role}</span>`
    : '';

  navLinks.innerHTML = `
    <a href="/courses">Courses</a>
    <span style="color:var(--border-hover);margin:0 2px;user-select:none">|</span>
    ${roleChip}
    ${roleChip ? '<span style="color:var(--border-hover);margin:0 2px;user-select:none">|</span>' : ''}
    <a href="#" onclick="logout()">Logout</a>
  `;
})();

function logout() {
  localStorage.removeItem('token');
  window.location.href = '/login';
}

// Helper used by all pages for authenticated API calls
function authHeaders() {
  const token = getToken();
  return {
    'Content-Type': 'application/json',
    ...(token ? { 'Authorization': `Bearer ${token}` } : {}),
  };
}
