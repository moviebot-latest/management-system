const CART_KEY = 'future-library-cart';
const $ = (selector) => document.querySelector(selector);
let books = [];
let cart = [];
let member = null;

function escapeHtml(value) {
  return String(value).replace(/[&<>"']/g, (character) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[character]);
}

async function request(url, options = {}) {
  const response = await fetch(url, { ...options, headers: { 'Content-Type': 'application/json', ...options.headers } });
  const result = await response.json();
  if (!response.ok) throw new Error(result.error || 'Something went wrong.');
  return result;
}

function persistCart() {
  localStorage.setItem(CART_KEY, JSON.stringify(cart));
}

function lineTotal(item) {
  const book = books.find((entry) => entry.id === item.bookId);
  return (item.mode === 'buy' ? book.buyPrice : book.rentPrice * (item.days || 7)) * item.quantity;
}

function render() {
  const items = cart.filter((item) => books.some((book) => book.id === item.bookId));
  $('#cartItemCount').textContent = `${items.reduce((sum, item) => sum + item.quantity, 0)} ${items.reduce((sum, item) => sum + item.quantity, 0) === 1 ? 'book' : 'books'}`;
  $('#cartItems').innerHTML = items.length ? items.map((item, index) => {
    const book = books.find((entry) => entry.id === item.bookId);
    const cover = book.isbn ? `<img class="cart-cover" src="https://covers.openlibrary.org/b/isbn/${encodeURIComponent(book.isbn)}-M.jpg?default=false" alt="" onerror="this.style.visibility='hidden'">` : `<span class="cart-cover cart-ncert-cover">${escapeHtml(book.subject || 'N')}</span>`;
    const terms = item.mode === 'buy' ? `Buy · $${book.buyPrice.toFixed(2)}` : `Rent · $${book.rentPrice.toFixed(2)} per day`;
    return `<article class="cart-line">${cover}<div class="cart-line-main"><span class="book-genre">${escapeHtml(book.genre)}</span><h3>${escapeHtml(book.title)}</h3><p>${escapeHtml(book.author)} · ${terms}</p>${item.mode === 'rent' ? `<label class="rental-days">Rental length <select data-days="${index}">${[3, 7, 14, 30].map((days) => `<option value="${days}" ${Number(item.days || 7) === days ? 'selected' : ''}>${days} days</option>`).join('')}</select></label>` : ''}<div class="quantity-controls"><button type="button" data-quantity="${index}" data-delta="-1" aria-label="Remove one copy">−</button><span>${item.quantity}</span><button type="button" data-quantity="${index}" data-delta="1" aria-label="Add one copy" ${item.quantity >= book.stock ? 'disabled' : ''}>+</button><button type="button" class="remove-line" data-remove="${index}">Remove</button></div></div><strong class="cart-line-total">$${lineTotal(item).toFixed(2)}</strong></article>`;
  }).join('') : '<div class="cart-empty"><span>▤</span><h3>Your bag has room for a good book.</h3><p>Choose something from the shelves and we’ll have it waiting at the library desk.</p><a class="portal-primary" href="/#books">Browse books <span>↗</span></a></div>';
  const total = items.reduce((sum, item) => sum + lineTotal(item), 0);
  $('#subtotal').textContent = `$${total.toFixed(2)}`;
  $('#cartTotal').textContent = `$${total.toFixed(2)}`;
  $('#placeOrder').disabled = !items.length || !member;
  $('#checkoutProfile').innerHTML = member ? `Collecting for <strong>${escapeHtml(member.name)}</strong> · ${escapeHtml(member.email)}` : 'Sign in before placing an order.';
  if (!member && items.length) $('#checkoutProfile').innerHTML += ' <a href="/account.html?next=%2Fcart.html">Sign in ↗</a>';
}

function showToast(message) {
  const toast = $('#portalToast');
  toast.textContent = message;
  toast.classList.add('show');
  setTimeout(() => toast.classList.remove('show'), 2800);
}

document.addEventListener('click', (event) => {
  const quantityButton = event.target.closest('[data-quantity]');
  if (quantityButton) {
    const index = Number(quantityButton.dataset.quantity);
    const delta = Number(quantityButton.dataset.delta);
    const book = books.find((entry) => entry.id === cart[index].bookId);
    cart[index].quantity = Math.max(0, Math.min(book.stock, cart[index].quantity + delta));
    if (!cart[index].quantity) cart.splice(index, 1);
    persistCart();
    render();
    return;
  }
  const removeButton = event.target.closest('[data-remove]');
  if (removeButton) {
    cart.splice(Number(removeButton.dataset.remove), 1);
    persistCart();
    render();
  }
});

document.addEventListener('change', (event) => {
  const daysSelect = event.target.closest('[data-days]');
  if (!daysSelect) return;
  cart[Number(daysSelect.dataset.days)].days = Number(daysSelect.value);
  persistCart();
  render();
});

$('#placeOrder').addEventListener('click', async () => {
  if (!member) return location.assign('/account.html?next=%2Fcart.html');
  try {
    const order = await request('/api/purchases', { method: 'POST', body: JSON.stringify({ items: cart, pickupLocation: 'main-desk', paymentMethod: $('#paymentChoice').value }) });
    cart = [];
    persistCart();
    $('#cartLayout').hidden = true;
    $('#orderSuccess').hidden = false;
    $('#orderSuccess').innerHTML = `<span class="success-mark">✓</span><p class="eyebrow">YOUR BOOKS ARE ON THEIR WAY</p><h2>We'll see you<br><em>at the desk.</em></h2><p>Order <strong>${escapeHtml(order.orderCode)}</strong> is ready for pickup at Future Library · Main desk. Ask a library team member for your order.</p><div class="pickup-ticket"><span>ORDER TOTAL</span><strong>$${order.total.toFixed(2)}</strong><span>${order.paymentStatus === 'demo-paid' ? 'Demo card recorded · no charge' : 'Pay at the desk · cash or card'}</span></div><a class="portal-primary" href="/">Back to the library <span>↗</span></a>`;
  } catch (error) { showToast(error.message); }
});

async function init() {
  try {
    cart = JSON.parse(localStorage.getItem(CART_KEY) || '[]');
    const [{ books: catalog }, { user }] = await Promise.all([request('/api/state'), request('/api/auth/me')]);
    books = catalog;
    member = user?.role === 'member' ? user : null;
    render();
  } catch (error) { showToast(error.message); }
}

init();
