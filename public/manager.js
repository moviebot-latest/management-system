const $ = (selector) => document.querySelector(selector);
let manager = null;
let state = null;

function escapeHtml(value) {
  return String(value).replace(/[&<>"']/g, (character) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[character]);
}

async function request(url, options = {}) {
  const response = await fetch(url, { ...options, headers: { 'Content-Type': 'application/json', ...options.headers } });
  const result = await response.json();
  if (!response.ok) throw new Error(result.error || 'Something went wrong.');
  return result;
}

function showToast(message) {
  const toast = $('#portalToast');
  toast.textContent = message;
  toast.classList.add('show');
  setTimeout(() => toast.classList.remove('show'), 2800);
}

function showLoginError(message) {
  $('#managerError').textContent = message;
  $('#managerError').hidden = false;
}

function renderManager() {
  $('#managerLoginPanel').hidden = true;
  $('#managerDashboard').hidden = false;
  $('#managerName').textContent = `${manager.name.split(' ')[0]}.`;
  const stats = state.stats;
  $('#managerStats').innerHTML = `<div><strong>${stats.books}</strong><span>available copies</span></div><div><strong>${stats.occupied}/${stats.total}</strong><span>seats occupied</span></div><div><strong>${state.orders.length}</strong><span>pickup orders</span></div><div><strong>${state.users.length}</strong><span>members</span></div>`;
  $('#managerBookList').innerHTML = state.books.map((book) => `<form class="manager-book-row" data-book-update="${escapeHtml(book.id)}"><div><strong>${escapeHtml(book.title)}</strong><span>${escapeHtml(book.author)} · ${escapeHtml(book.genre)}</span></div><label>Copies<input name="stock" type="number" min="0" max="500" value="${book.stock}" required></label><button type="submit" aria-label="Update stock for ${escapeHtml(book.title)}">Save</button></form>`).join('');
  const rows = Array.from({ length: Math.ceil(state.seats.length / 10) }, (_, index) => state.seats.slice(index * 10, index * 10 + 10));
  $('#managerSeatCount').textContent = `${state.seats.length} SEATS`;
  $('#managerSeatMap').innerHTML = rows.map((seats, index) => `<div class="manager-seat-row"><span class="row-label">ROW ${String.fromCharCode(65 + index)}</span>${seats.map((seat) => `<button class="manager-seat ${seat.status}" data-seat-id="${seat.id}" aria-label="${seat.id} · ${seat.status}" title="${seat.id} · ${seat.status}">${seat.id.slice(1)}</button>`).join('')}</div>`).join('');
  $('#orderCount').textContent = `${state.orders.length} ORDERS`;
  $('#managerOrderList').innerHTML = state.orders.length ? [...state.orders].reverse().map((order) => `<article class="manager-order"><div><strong>${escapeHtml(order.customer.name)}</strong><span>${escapeHtml(order.customer.email)} · ${new Date(order.createdAt).toLocaleString()}</span></div><div><strong>${escapeHtml(order.orderCode)} · $${order.total.toFixed(2)}</strong><span>${escapeHtml(order.items.map((item) => `${item.quantity} × ${item.title}`).join(', '))}</span></div><span class="order-state">${escapeHtml(order.paymentStatus)} · ${escapeHtml(order.status)}</span></article>`).join('') : '<p class="empty-manager">No pickup orders yet.</p>';
}

async function loadDashboard() {
  const result = await request('/api/manager/state');
  state = result;
  renderManager();
}

$('#managerLoginForm').addEventListener('submit', async (event) => {
  event.preventDefault();
  $('#managerError').hidden = true;
  try {
    const response = await request('/api/auth/login', { method: 'POST', body: JSON.stringify({ email: $('#managerEmail').value, password: $('#managerPassword').value, portal: 'manager' }) });
    manager = response.user;
    await loadDashboard();
  } catch (error) { showLoginError(error.message); }
});

$('#managerLogout').addEventListener('click', async () => {
  await request('/api/auth/logout', { method: 'POST' });
  location.reload();
});

$('#newBookForm').addEventListener('submit', async (event) => {
  event.preventDefault();
  const form = new FormData(event.currentTarget);
  const body = Object.fromEntries(form.entries());
  for (const field of ['stock', 'buyPrice', 'rentPrice']) body[field] = Number(body[field]);
  try {
    await request('/api/manager/books', { method: 'POST', body: JSON.stringify(body) });
    event.currentTarget.reset();
    await loadDashboard();
    showToast('New title added to the shelves.');
  } catch (error) { showToast(error.message); }
});

document.addEventListener('submit', async (event) => {
  const form = event.target.closest('[data-book-update]');
  if (!form) return;
  event.preventDefault();
  try {
    const stock = Number(new FormData(form).get('stock'));
    await request(`/api/manager/books/${encodeURIComponent(form.dataset.bookUpdate)}`, { method: 'PATCH', body: JSON.stringify({ stock }) });
    await loadDashboard();
    showToast('Shelf count updated.');
  } catch (error) { showToast(error.message); }
});

document.addEventListener('click', async (event) => {
  const seat = event.target.closest('[data-seat-id]');
  if (!seat) return;
  const nextStatus = seat.classList.contains('occupied') ? 'available' : 'occupied';
  if (seat.classList.contains('reserved')) return showToast('This seat has a live member reservation.');
  try {
    await request(`/api/manager/seats/${encodeURIComponent(seat.dataset.seatId)}`, { method: 'PATCH', body: JSON.stringify({ status: nextStatus }) });
    await loadDashboard();
    showToast(`${seat.dataset.seatId} marked ${nextStatus}.`);
  } catch (error) { showToast(error.message); }
});

async function init() {
  try {
    const result = await request('/api/auth/me');
    if (result.user?.role === 'manager') {
      manager = result.user;
      await loadDashboard();
    } else if (result.user?.role === 'member') {
      showLoginError('This is the staff room. Sign in with a manager account.');
    }
  } catch (error) { showLoginError(error.message); }
}

init();
