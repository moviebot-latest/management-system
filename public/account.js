const $ = (selector) => document.querySelector(selector);
const params = new URLSearchParams(location.search);
const nextPath = params.get('next');
const redirectAfterAuth = nextPath && nextPath.startsWith('/') && !nextPath.startsWith('//') ? nextPath : '/';
let mode = 'signin';
let user = null;

function escapeHtml(value) {
  return String(value).replace(/[&<>"']/g, (character) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[character]);
}

function showError(message) {
  $('#accountError').textContent = message;
  $('#accountError').hidden = false;
}

function setMode(nextMode) {
  mode = nextMode;
  const registering = mode === 'register';
  $('#signinTab').classList.toggle('active', !registering);
  $('#registerTab').classList.toggle('active', registering);
  $('#signinTab').setAttribute('aria-selected', String(!registering));
  $('#registerTab').setAttribute('aria-selected', String(registering));
  document.querySelectorAll('.register-only').forEach((field) => { field.hidden = !registering; });
  $('#formTitle').textContent = registering ? 'Let’s make this yours.' : 'Welcome back.';
  $('#formDescription').textContent = registering ? 'Tell us a little about yourself to get your library card.' : 'Pick up right where you left off.';
  $('#submitAccount').innerHTML = `${registering ? 'Create my account' : 'Sign in'} <span>↗</span>`;
  $('#memberPassword').autocomplete = registering ? 'new-password' : 'current-password';
  $('#accountError').hidden = true;
}

async function request(url, options = {}) {
  const response = await fetch(url, { ...options, headers: { 'Content-Type': 'application/json', ...options.headers } });
  const result = await response.json();
  if (!response.ok) throw new Error(result.error || 'Something went wrong.');
  return result;
}

function renderProfile() {
  $('#accountForm').hidden = true;
  $('#accountProfile').hidden = false;
  $('#accountProfile').innerHTML = `<p class="eyebrow">YOUR LIBRARY CARD</p><h2>Good to see you,<br><em>${escapeHtml(user.name.split(' ')[0])}.</em></h2><div class="profile-details"><div><span>EMAIL</span><strong>${escapeHtml(user.email)}</strong></div><div><span>PHONE</span><strong>${escapeHtml(user.phone || 'Not added')}</strong></div><div><span>COURSE / CLASS</span><strong>${escapeHtml(user.course || 'Not added')}</strong></div></div><a class="portal-primary profile-link" href="/">Back to the library <span>↗</span></a><button class="portal-quiet-button profile-logout" id="memberLogout">Sign out</button>`;
}

document.querySelectorAll('[data-mode]').forEach((tab) => tab.addEventListener('click', () => setMode(tab.dataset.mode)));
$('#accountForm').addEventListener('submit', async (event) => {
  event.preventDefault();
  $('#accountError').hidden = true;
  const form = new FormData(event.currentTarget);
  const registering = mode === 'register';
  const body = registering
    ? { name: form.get('name'), email: form.get('email'), phone: form.get('phone'), course: form.get('course'), password: form.get('password') }
    : { email: form.get('email'), password: form.get('password') };
  try {
    const result = await request(registering ? '/api/auth/register' : '/api/auth/login', { method: 'POST', body: JSON.stringify(body) });
    user = result.user;
    location.assign(redirectAfterAuth);
  } catch (error) { showError(error.message); }
});

document.addEventListener('click', async (event) => {
  if (event.target.closest('#memberLogout')) {
    await request('/api/auth/logout', { method: 'POST' });
    user = null;
    $('#accountProfile').hidden = true;
    $('#accountForm').hidden = false;
    setMode('signin');
  }
});

request('/api/auth/me').then(({ user: currentUser }) => {
  user = currentUser;
  if (user?.role === 'manager') return location.replace('/manager.html');
  if (user) renderProfile();
}).catch(() => {});
