const data = { seats: [], books: [], rentals: [], purchases: [], stats: {}, user: null, cart: [], selectedSeat: null, booking: null, mode: 'rent', view: 'home' };
const CART_KEY = 'future-library-cart';
const bookingKey = () => `future-library-booking-${data.user?.id || 'guest'}`;
const persistBooking = () => localStorage.setItem(bookingKey(), JSON.stringify(data.booking));
const coverColors = ['#405a4a', '#9a6244', '#b2a558', '#344b64', '#8d655d', '#596b52', '#5c4264', '#516a72'];
const $ = (selector, root = document) => root.querySelector(selector);
const $$ = (selector, root = document) => [...root.querySelectorAll(selector)];

async function api(url, options = {}) {
  const response = await fetch(url, { ...options, headers: { 'Content-Type': 'application/json', ...options.headers } });
  const result = await response.json();
  if (!response.ok) throw new Error(result.error || 'Something went wrong. Please try again.');
  return result;
}

function escapeHtml(value) {
  return String(value).replace(/[&<>"']/g, (character) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[character]);
}

function showToast(message) {
  const toast = $('#toast');
  toast.textContent = message;
  toast.classList.add('show');
  clearTimeout(showToast.timer);
  showToast.timer = setTimeout(() => toast.classList.remove('show'), 2900);
}


function animateMetric(element, target) {
  if (!element) return;
  const next = Number(target) || 0;
  const previous = Number(element.dataset.metricValue);
  if (previous === next) return;
  element.dataset.metricValue = String(next);
  if (window.matchMedia('(prefers-reduced-motion: reduce)').matches || !Number.isFinite(previous)) {
    element.textContent = next.toLocaleString();
    return;
  }
  const start = Number.isFinite(previous) ? previous : 0;
  const started = performance.now();
  const duration = 700;
  const tick = (now) => {
    const progress = Math.min(1, (now - started) / duration);
    const eased = 1 - Math.pow(1 - progress, 3);
    element.textContent = Math.round(start + (next - start) * eased).toLocaleString();
    if (progress < 1) requestAnimationFrame(tick);
  };
  requestAnimationFrame(tick);
}

function setupHomeMotion() {
  const home = $('#homeView');
  if (!home || home.dataset.motionReady) return;
  home.dataset.motionReady = 'true';
  const revealTargets = [
    ...home.querySelectorAll('.photo-rail, .entry-section, .how-section, .credibility-band, .home-footer'),
    ...home.querySelectorAll('.entry-card, .step, .credibility-band>div')
  ];
  revealTargets.forEach((element) => element.classList.add('home-reveal'));

  if ('IntersectionObserver' in window && !window.matchMedia('(prefers-reduced-motion: reduce)').matches) {
    const observer = new IntersectionObserver((entries) => {
      entries.forEach((entry) => {
        if (entry.isIntersecting) {
          entry.target.classList.add('is-visible');
          observer.unobserve(entry.target);
        }
      });
    }, { threshold: .14, rootMargin: '0px 0px -35px 0px' });
    revealTargets.forEach((element) => observer.observe(element));
  } else {
    revealTargets.forEach((element) => element.classList.add('is-visible'));
  }

  const finePointer = window.matchMedia('(hover:hover) and (pointer:fine)').matches;
  if (finePointer && !window.matchMedia('(prefers-reduced-motion: reduce)').matches) {
    home.querySelectorAll('.entry-card, .photo-card').forEach((card) => {
      card.addEventListener('pointermove', (event) => {
        const rect = card.getBoundingClientRect();
        const x = (event.clientX - rect.left) / rect.width - .5;
        const y = (event.clientY - rect.top) / rect.height - .5;
        card.style.transform = `perspective(800px) rotateX(${(-y * 3).toFixed(2)}deg) rotateY(${(x * 4).toFixed(2)}deg) translateY(-5px)`;
      });
      card.addEventListener('pointerleave', () => { card.style.transform = ''; });
    });
  }
}

function updateHomeParallax() {
  if (data.view !== 'home' || window.matchMedia('(prefers-reduced-motion: reduce)').matches) return;
  const hero = $('#homeView .hero');
  if (!hero) return;
  const y = Math.min(window.scrollY, 260);
  hero.style.setProperty('--hero-shift', `${Math.round(y * .055)}px`);
}

function updateScrollProgress() {
  const progress = $('#scrollProgress');
  if (!progress) return;
  const max = document.documentElement.scrollHeight - window.innerHeight;
  progress.style.width = `${max > 0 ? Math.min(100, Math.max(0, window.scrollY / max * 100)) : 0}%`;
}

function switchView(view) {
  data.view = view;
  if (location.hash !== `#${view}`) history.replaceState(null, '', `#${view}`);
  $$('[data-view-panel]').forEach((panel) => {
    const active = panel.dataset.viewPanel === view;
    panel.hidden = !active;
    panel.classList.toggle('active', active);
  });
  $$('.nav-link').forEach((link) => link.classList.toggle('active', link.dataset.view === view));
  if (view === 'shelf') renderShelf();
  if (view === 'seats') renderSeats();
  if (view === 'books') renderBooks();
  if (view === 'home') setupHomeMotion();
  window.scrollTo({ top: 0, behavior: 'smooth' });
}

function renderStatus() {
  const stats = data.stats;
  $('#liveSeats').textContent = `${stats.occupied} seats occupied · ${stats.total - stats.occupied - stats.reserved} free`;
  $('#liveBooks').textContent = `${stats.books.toLocaleString()} books ready to explore`;
  $('#seatSummary').textContent = `${stats.occupied} / ${stats.total}`;
  $('#streakCount').textContent = stats.streak || 4;
  animateMetric($('#footerSeatCount'), stats.total);
  animateMetric($('#footerCopyCount'), stats.books);
  animateMetric($('#footerTitleCount'), data.books.length);
  $('#liveUpdated').textContent = `LIVE · UPDATED ${new Date().toLocaleTimeString([], { hour: 'numeric', minute: '2-digit' }).toUpperCase()}`;
  $('#bagCount').textContent = data.cart.reduce((total, item) => total + item.quantity, 0);
  $('#authLink').textContent = data.user ? data.user.name.split(' ')[0] : 'Sign in';
  $('#authLink').href = data.user ? '/account.html' : '/account.html';
}

function renderSeats() {
  const map = $('#seatMap');
  if (!map) return;
  const rows = Array.from({ length: Math.ceil(data.seats.length / 10) }, (_, index) => data.seats.slice(index * 10, index * 10 + 10));
  map.innerHTML = rows.map((seats, index) => `<div class="seat-row"><span class="seat-row-label">ROW ${String.fromCharCode(65 + index)}</span>${seats.map((seat) => {
    const title = seat.status === 'occupied' ? `Occupied since ${seat.occupiedSince || 'earlier today'}` : seat.status === 'reserved' ? 'Reserved for another reader' : 'Available, select to reserve';
    const selected = data.selectedSeat === seat.id;
    return `<button type="button" class="seat-tile ${seat.status}${selected ? ' selected' : ''}" data-seat="${seat.id}" ${seat.status === 'reserved' ? 'disabled' : ''} aria-label="Seat ${seat.id}: ${escapeHtml(title)}" title="Seat ${seat.id} · ${escapeHtml(title)}">${seat.id.slice(1)}</button>`;
  }).join('')}</div>`).join('');
  $('#bookSeatButton').disabled = !data.selectedSeat;
}

function renderBooks() {
  const query = ($('#bookSearch')?.value || '').trim().toLowerCase();
  const genre = $('#genreFilter')?.value || 'all';
  const books = data.books.filter((book) => (genre === 'all' || book.genre === genre) && `${book.title} ${book.author} ${book.genre}`.toLowerCase().includes(query));
  $('#bookResultCount').textContent = `${books.length} ${books.length === 1 ? 'good read' : 'good reads'}`;
  const grid = $('#bookGrid');
  if (!grid) return;
  grid.innerHTML = books.length ? books.map((book) => {
    const color = coverColors[data.books.indexOf(book) % coverColors.length];
    const price = data.mode === 'buy' ? `$${book.buyPrice.toFixed(2)}` : `$${book.rentPrice.toFixed(2)} <small>/ day</small>`;
    const unavailable = book.stock < 1;
    return `<article class="book-card">
      <div class="book-cover-wrap" style="--cover-color:${color}">
        <div class="book-cover-fallback${book.collection === 'NCERT' ? ' ncert-cover' : ''}" aria-hidden="true">${book.collection === 'NCERT' ? `<span>NCERT</span><strong>${escapeHtml(book.subject)}</strong><small>${escapeHtml(book.level)}</small>` : escapeHtml(book.title)}</div>
        ${book.isbn ? `<img class="book-cover" src="https://covers.openlibrary.org/b/isbn/${encodeURIComponent(book.isbn)}-L.jpg?default=false" alt="Cover of ${escapeHtml(book.title)}" loading="lazy" onerror="this.remove()">` : ''}
        <span class="stock-tag ${unavailable ? 'sold-out' : ''}">${unavailable ? 'Currently out' : `${book.stock} ${book.stock === 1 ? 'copy' : 'copies'} left`}</span>
      </div>
      <div class="book-details"><span class="book-genre">${escapeHtml(book.genre)}</span><h3>${escapeHtml(book.title)}</h3><p class="book-author">${escapeHtml(book.author)}</p>
      <div class="book-actions"><span class="book-price">${price}</span><button type="button" class="add-book" data-add-book="${book.id}" aria-label="Add ${escapeHtml(book.title)} to bag" ${unavailable ? 'disabled' : ''}>+</button></div></div>
    </article>`;
  }).join('') : '<p class="empty-results">Nothing on these shelves just yet. Try another search.</p>';
}

function renderShelf() {
  const rentals = data.rentals.filter((rental) => !rental.returnedAt);
  $('#rentalCount').textContent = rentals.length;
  $('#passCount').textContent = data.booking && !data.booking.releasedAt ? '1' : '0';
  $('#rentalsList').innerHTML = rentals.length ? rentals.map((rental) => {
    const remaining = Math.max(0, new Date(rental.dueAt).getTime() - Date.now());
    const days = Math.ceil(remaining / 86_400_000);
    const late = remaining === 0;
    const percent = Math.max(5, Math.min(100, (days / 30) * 100));
    const isbn = data.books.find((book) => book.id === rental.bookId)?.isbn;
    const cover = isbn ? `<img class="shelf-book-cover" src="https://covers.openlibrary.org/b/isbn/${encodeURIComponent(isbn)}-S.jpg?default=false" alt="" onerror="this.style.visibility='hidden'">` : '<span class="shelf-book-cover shelf-ncert-cover">N</span>';
    return `<article class="shelf-item">${cover}<div class="shelf-item-main"><strong>${escapeHtml(rental.title)}</strong><p>${late ? 'Due today · $0.50 late fee per day' : `Due in ${days} ${days === 1 ? 'day' : 'days'}`}</p><div class="due-meter"><span style="width:${percent}%"></span></div><button class="small-action" data-return-rental="${rental.id}">Return book</button></div></article>`;
  }).join('') : '<p class="shelf-empty">No books on loan right now. The shelves are full of possibility.</p>';
  const booking = data.booking;
  const activePass = booking && !booking.releasedAt;
  $('#passesList').innerHTML = activePass ? `<article class="shelf-item"><span class="pass-code">⌖</span><div class="shelf-item-main"><strong>Seat ${escapeHtml(booking.seatId)}</strong><p>${booking.checkedInAt ? `Checked in · until ${new Date(booking.endsAt).toLocaleTimeString([], { hour: 'numeric', minute: '2-digit' })}` : `Held for 15 min · ${booking.durationHours} hour booking`}</p>${booking.checkedInAt ? `<button class="small-action" data-release-seat="${booking.code}">Check out &amp; release seat</button>` : `<button class="small-action" data-show-pass="true">Open seat pass</button>`}</div></article>` : '<p class="shelf-empty">Your next study session is just a seat away.</p>';
}

function setState(next) {
  data.seats = next.seats;
  data.books = next.books;
  data.rentals = next.rentals || [];
  data.purchases = next.purchases || [];
  data.stats = next.stats;
  renderStatus();
  renderSeats();
  renderBooks();
  if (data.view === 'shelf') renderShelf();
}

function setModal(content) {
  $('#modalBody').innerHTML = content;
  $('#modalBackdrop').hidden = false;
  $('#modalClose').focus();
}

function closeModal() {
  $('#modalBackdrop').hidden = true;
}

function passMarkup(booking) {
  const checkInUrl = `${location.origin}/api/checkin?booking=${encodeURIComponent(booking.code)}`;
  const qrUrl = `https://api.qrserver.com/v1/create-qr-code/?size=240x240&margin=0&data=${encodeURIComponent(checkInUrl)}`;
  return `<div class="pass-success"><span class="eyebrow">YOUR READING ROOM PASS</span><h2>Seat ${escapeHtml(booking.seatId)} is yours.</h2><p class="modal-copy">Show this code when you arrive. Your reservation is held for 15 minutes.</p><div class="qr-frame"><img src="${qrUrl}" alt="QR code to check in to seat ${escapeHtml(booking.seatId)}"></div><span class="pass-number">${escapeHtml(booking.code)}</span><p class="modal-copy">${booking.durationHours} hour booking · tap check in on arrival</p><div class="pass-actions"><button class="primary-button" data-checkin="${booking.code}">Check in now <span aria-hidden="true">↗</span></button><button class="pass-secondary" data-close-modal>Done</button></div></div>`;
}

function openCart() {
  if (!data.cart.length) {
    setModal('<p class="eyebrow">A LITTLE SPACE FOR SOMETHING GOOD</p><h2>Your bag is waiting.</h2><p class="modal-copy">The next favorite is only a few shelves away.</p><button class="primary-button" data-view="books">Explore the bookshop <span aria-hidden="true">↗</span></button>');
    return;
  }
  const total = data.cart.reduce((sum, item) => {
    const book = data.books.find((entry) => entry.id === item.bookId);
    return sum + (item.mode === 'buy' ? book.buyPrice : book.rentPrice * item.days) * item.quantity;
  }, 0);
  setModal(`<p class="eyebrow">A FEW GOOD THINGS</p><h2>Your bag.</h2><div class="cart-items">${data.cart.map((item, index) => {
    const book = data.books.find((entry) => entry.id === item.bookId);
    const label = item.mode === 'buy' ? `Buy · $${book.buyPrice.toFixed(2)}` : `Rent · ${item.days} days · $${(book.rentPrice * item.days).toFixed(2)}`;
    return `<div class="cart-row"><strong>${escapeHtml(book.title)}</strong><span>${label} · Qty ${item.quantity}</span><button data-remove-cart="${index}">Remove</button></div>`;
  }).join('')}</div><div class="cart-total"><span>Subtotal</span><span>$${total.toFixed(2)}</span></div><p class="modal-copy">A secure, prototype checkout. No payment details needed.</p><button class="primary-button" data-checkout>Complete checkout <span aria-hidden="true">↗</span></button>`);
}

function populateGenres() {
  const genres = [...new Set(data.books.map((book) => book.genre))].sort();
  $('#genreFilter').innerHTML = '<option value="all">All genres</option>' + genres.map((genre) => `<option value="${escapeHtml(genre)}">${escapeHtml(genre)}</option>`).join('');
}

document.addEventListener('click', async (event) => {
  const viewLink = event.target.closest('[data-view]');
  if (viewLink) {
    event.preventDefault();
    const view = viewLink.dataset.view;
    switchView(view);
    return;
  }
  const seatTile = event.target.closest('[data-seat]');
  if (seatTile) {
    const seat = data.seats.find((item) => item.id === seatTile.dataset.seat);
    if (seat?.status === 'occupied') showToast(`Seat ${seat.id} has been occupied since ${seat.occupiedSince || 'earlier today'}.`);
    else if (seat?.status === 'available') {
      data.selectedSeat = seat.id;
      renderSeats();
      $('#bookingPanel').querySelector('h2').innerHTML = `Seat ${escapeHtml(seat.id)}<br>looks good.`;
      $('#bookingPanel').querySelector('.booking-panel>p:not(.eyebrow):not(.panel-footnote)').textContent = 'A little space to focus, held just for you.';
    }
    return;
  }
  const modeButton = event.target.closest('[data-mode]');
  if (modeButton) {
    data.mode = modeButton.dataset.mode;
    $$('.mode-button').forEach((button) => button.classList.toggle('active', button === modeButton));
    renderBooks();
    return;
  }
  const addButton = event.target.closest('[data-add-book]');
  if (addButton) {
    if (!data.user || data.user.role !== 'member') {
      setModal('<p class="eyebrow">A LIBRARY CARD FIRST</p><h2>Let’s make this order yours.</h2><p class="modal-copy">Sign in or create a member account before adding books to your bag. Your details help the library team prepare your pickup.</p><a class="primary-button" href="/account.html?next=%2F%23books">Continue to sign in <span aria-hidden="true">↗</span></a>');
      return;
    }
    const book = data.books.find((entry) => entry.id === addButton.dataset.addBook);
    const days = data.mode === 'rent' ? 7 : null;
    const existing = data.cart.find((item) => item.bookId === book.id && item.mode === data.mode && item.days === days);
    if (existing) existing.quantity += 1;
    else data.cart.push({ bookId: book.id, mode: data.mode, days, quantity: 1 });
    localStorage.setItem(CART_KEY, JSON.stringify(data.cart));
    renderStatus();
    setModal(`<p class="eyebrow">ONE FOR YOUR BAG</p><h2>${escapeHtml(book.title)}<br>is coming along.</h2><p class="modal-copy">Added ${data.mode === 'rent' ? 'as a 7-day rental' : 'to your purchase list'}.</p><div class="pass-actions"><a class="primary-button" href="/cart.html">Go to your bag <span aria-hidden="true">↗</span></a><button class="pass-secondary" data-close-modal>Keep browsing</button></div>`);
    return;
  }
  if (event.target.closest('[data-remove-cart]')) {
    data.cart.splice(Number(event.target.closest('[data-remove-cart]').dataset.removeCart), 1);
    localStorage.setItem(CART_KEY, JSON.stringify(data.cart));
    renderStatus();
    return openCart();
  }
  if (event.target.closest('[data-checkout]')) {
    try {
      const order = await api('/api/purchases', { method: 'POST', body: JSON.stringify({ items: data.cart }) });
      data.cart = [];
      closeModal();
      showToast(`You're all set. Order ${order.orderCode} · $${order.total.toFixed(2)}.`);
      await refreshState();
    } catch (error) { showToast(error.message); }
    return;
  }
  if (event.target.closest('[data-close-modal]')) return closeModal();
  if (event.target.closest('[data-checkin]')) {
    try {
      const bookingCode = event.target.closest('[data-checkin]').dataset.checkin;
      await api('/api/checkin', { method: 'POST', body: JSON.stringify({ bookingCode }) });
      if (data.booking) data.booking.checkedInAt = new Date().toISOString();
      persistBooking();
      closeModal();
      showToast(`Checked in to seat ${data.booking.seatId}. Settle in.`);
      await refreshState();
    } catch (error) { showToast(error.message); }
    return;
  }
  if (event.target.closest('[data-show-pass]') && data.booking) return setModal(passMarkup(data.booking));
  if (event.target.closest('[data-release-seat]')) {
    try {
      await api('/api/checkout', { method: 'POST', body: JSON.stringify({ bookingCode: event.target.closest('[data-release-seat]').dataset.releaseSeat }) });
      data.booking.releasedAt = new Date().toISOString();
      persistBooking();
      showToast('Your seat is free for the next reader.');
      await refreshState();
    } catch (error) { showToast(error.message); }
    return;
  }
  if (event.target.closest('[data-return-rental]')) {
    try {
      await api(`/api/rentals/${event.target.closest('[data-return-rental]').dataset.returnRental}/return`, { method: 'POST' });
      showToast('Book returned. Thank you for sharing the shelf.');
      await refreshState();
    } catch (error) { showToast(error.message); }
    return;
  }
  if (event.target.closest('#bookSeatButton')) {
    if (!data.user || data.user.role !== 'member') {
      setModal('<p class="eyebrow">YOUR READING ROOM PASS</p><h2>A seat with your name on it.</h2><p class="modal-copy">Sign in or create a member account to book a seat. We’ll ask for your name and a few details just once.</p><a class="primary-button" href="/account.html?next=%2F%23seats">Continue to sign in <span aria-hidden="true">↗</span></a>');
      return;
    }
    try {
      const booking = await api('/api/bookings', { method: 'POST', body: JSON.stringify({ seatId: data.selectedSeat, durationHours: Number($('#durationSelect').value) }) });
      data.booking = booking;
      persistBooking();
      data.selectedSeat = null;
      setModal(passMarkup(booking));
      await refreshState();
    } catch (error) { showToast(error.message); }
    return;
  }
  if (event.target.closest('#modalClose') || event.target.id === 'modalBackdrop') closeModal();
});

$('#bookSearch').addEventListener('input', renderBooks);
$('#genreFilter').addEventListener('change', renderBooks);
$('#focusToggle').addEventListener('click', () => {
  document.body.classList.toggle('focus-mode');
  $('#focusToggle').setAttribute('aria-pressed', String(document.body.classList.contains('focus-mode')));
});
const backToTop = $('#backToTop');
const updateBackToTop = () => { backToTop.hidden = window.scrollY < 480; };
window.addEventListener('scroll', updateBackToTop, { passive: true });
window.addEventListener('scroll', updateHomeParallax, { passive: true });
window.addEventListener('scroll', updateScrollProgress, { passive: true });
window.addEventListener('resize', updateScrollProgress, { passive: true });
backToTop.addEventListener('click', () => window.scrollTo({ top: 0, behavior: 'smooth' }));
updateBackToTop();
updateHomeParallax();
updateScrollProgress();
$('#modalClose').addEventListener('click', closeModal);
document.addEventListener('keydown', (event) => { if (event.key === 'Escape') closeModal(); });

async function refreshState() {
  try { setState(await api('/api/state')); }
  catch (error) { showToast(error.message); }
}

async function init() {
  try {
    const [initial, account] = await Promise.all([api('/api/state'), api('/api/auth/me')]);
    data.user = account.user;
    data.cart = JSON.parse(localStorage.getItem(CART_KEY) || '[]');
    try { data.booking = JSON.parse(localStorage.getItem(bookingKey()) || 'null'); }
    catch { data.booking = null; }
    populateGenres();
    setState(initial);
    setupHomeMotion();
    if (data.view === 'shelf') renderShelf();
    const requestedView = location.hash.slice(1);
    if (['home', 'seats', 'books', 'shelf'].includes(requestedView)) switchView(requestedView);
    const events = new EventSource('/api/events');
    events.onmessage = (message) => setState(JSON.parse(message.data));
    events.onerror = () => { $('#liveUpdated').textContent = 'RECONNECTING · LIVE STATUS'; };
  } catch {
    $('#liveSeats').textContent = 'Reading room temporarily unavailable';
    $('#liveBooks').textContent = 'Please refresh in a moment';
  }
}

init();