const http = require('node:http');
const fs = require('node:fs');
const path = require('node:path');
const { randomBytes, scryptSync, timingSafeEqual } = require('node:crypto');

const PORT = Number(process.env.PORT || 3000);
const publicDir = path.join(__dirname, 'public');
const streamClients = new Map();
const sessions = new Map();

function hashPassword(password, salt = randomBytes(16).toString('hex')) {
  return { salt, passwordHash: scryptSync(password, salt, 64).toString('hex') };
}

function verifyPassword(password, user) {
  const candidate = scryptSync(password, user.salt, 64);
  return timingSafeEqual(candidate, Buffer.from(user.passwordHash, 'hex'));
}

const state = {
  seats: Array.from({ length: 60 }, (_, index) => {
    const number = index + 1;
    const occupied = number <= 22;
    const reserved = number > 22 && number <= 26;
    return {
      id: `A${String(number).padStart(2, '0')}`,
      status: occupied ? 'occupied' : reserved ? 'reserved' : 'available',
      occupiedSince: occupied ? `${9 + Math.floor((number - 1) / 6)}:${String((number * 7) % 60).padStart(2, '0')} AM` : null,
      bookingCode: null,
    };
  }),
  books: [
    { id: 'bk-01', title: 'The Creative Act', author: 'Rick Rubin', genre: 'Creativity', isbn: '9780593652886', buyPrice: 28, rentPrice: 4, stock: 5 },
    { id: 'bk-02', title: 'Tomorrow, and Tomorrow, and Tomorrow', author: 'Gabrielle Zevin', genre: 'Fiction', isbn: '9780593321201', buyPrice: 19, rentPrice: 3, stock: 4 },
    { id: 'bk-03', title: 'Atomic Habits', author: 'James Clear', genre: 'Growth', isbn: '9780735211292', buyPrice: 18, rentPrice: 2.5, stock: 8 },
    { id: 'bk-04', title: 'The Design of Everyday Things', author: 'Don Norman', genre: 'Design', isbn: '9780465050659', buyPrice: 24, rentPrice: 3.5, stock: 3 },
    { id: 'bk-05', title: 'Educated', author: 'Tara Westover', genre: 'Memoir', isbn: '9780399590504', buyPrice: 17, rentPrice: 2.5, stock: 6 },
    { id: 'bk-06', title: 'Braiding Sweetgrass', author: 'Robin Wall Kimmerer', genre: 'Nature', isbn: '9781571313560', buyPrice: 20, rentPrice: 3, stock: 2 },
    { id: 'bk-07', title: 'A Little Life', author: 'Hanya Yanagihara', genre: 'Fiction', isbn: '9780804172707', buyPrice: 21, rentPrice: 3, stock: 0 },
    { id: 'bk-08', title: 'Ways of Seeing', author: 'John Berger', genre: 'Art', isbn: '9780140135152', buyPrice: 16, rentPrice: 2, stock: 7 },
    { id: 'ncert-10-mathematics', title: 'Mathematics: Textbook for Class X', author: 'NCERT', genre: 'NCERT · Class X', collection: 'NCERT', subject: 'Mathematics', level: 'CLASS X', buyPrice: 8, rentPrice: 1, stock: 12 },
    { id: 'ncert-10-science', title: 'Science: Textbook for Class X', author: 'NCERT', genre: 'NCERT · Class X', collection: 'NCERT', subject: 'Science', level: 'CLASS X', buyPrice: 9, rentPrice: 1, stock: 10 },
    { id: 'ncert-12-physics-1', title: 'Physics Part I: Textbook for Class XII', author: 'NCERT', genre: 'NCERT · Class XII', collection: 'NCERT', subject: 'Physics', level: 'CLASS XII · PART I', buyPrice: 10, rentPrice: 1.25, stock: 8 },
    { id: 'ncert-12-chemistry-1', title: 'Chemistry Part I: Textbook for Class XII', author: 'NCERT', genre: 'NCERT · Class XII', collection: 'NCERT', subject: 'Chemistry', level: 'CLASS XII · PART I', buyPrice: 10, rentPrice: 1.25, stock: 8 },
  ],
  bookings: [],
  rentals: [],
  purchases: [],
  orders: [],
  users: [],
};

const managerCredentials = hashPassword(process.env.MANAGER_PASSWORD || 'librarymanager123');
state.users.push({
  id: 'manager-1',
  name: 'Library Manager',
  email: (process.env.MANAGER_EMAIL || 'manager@futurelibrary.local').toLowerCase(),
  phone: '',
  course: '',
  role: 'manager',
  ...managerCredentials,
});

function publicUser(user) {
  if (!user) return null;
  return { id: user.id, name: user.name, email: user.email, phone: user.phone, course: user.course, role: user.role };
}

function currentUser(request) {
  const cookie = request.headers.cookie || '';
  const token = cookie.split(';').map((part) => part.trim()).find((part) => part.startsWith('future_library_session='))?.split('=')[1];
  const userId = token && sessions.get(token);
  return userId ? state.users.find((user) => user.id === userId) || null : null;
}

function startSession(response, user) {
  const token = randomBytes(32).toString('hex');
  sessions.set(token, user.id);
  response.setHeader('Set-Cookie', `future_library_session=${token}; HttpOnly; SameSite=Lax; Path=/; Max-Age=604800`);
}

function requireRole(request, response, roles = ['member', 'manager']) {
  const user = currentUser(request);
  if (!user) {
    sendJson(response, 401, { error: 'Sign in to continue.' });
    return null;
  }
  if (!roles.includes(user.role)) {
    sendJson(response, 403, { error: 'This action requires manager access.' });
    return null;
  }
  return user;
}

function inventoryFor(book) {
  const rented = state.rentals.filter((rental) => rental.bookId === book.id && !rental.returnedAt).length;
  return Math.max(0, book.stock - rented);
}

function snapshot(user = null) {
  const seats = state.seats.map(({ bookingCode, ...seat }) => seat);
  const canViewAll = user?.role === 'manager';
  const belongsToUser = (record) => canViewAll || (user && record.userId === user.id);
  return {
    seats,
    books: state.books.map((book) => ({ ...book, stock: inventoryFor(book) })),
    rentals: state.rentals.filter(belongsToUser),
    purchases: state.purchases.filter(belongsToUser),
    bookings: state.bookings.filter(belongsToUser).map(({ userId, userName, ...booking }) => booking),
    stats: {
      occupied: state.seats.filter((seat) => seat.status === 'occupied').length,
      reserved: state.seats.filter((seat) => seat.status === 'reserved').length,
      total: state.seats.length,
      books: state.books.reduce((sum, book) => sum + inventoryFor(book), 0),
      streak: 4,
    },
  };
}

function broadcast() {
  for (const [client, user] of streamClients) client.write(`data: ${JSON.stringify(snapshot(user))}\n\n`);
}

function sendJson(response, statusCode, data) {
  response.writeHead(statusCode, { 'Content-Type': 'application/json; charset=utf-8', 'Cache-Control': 'no-store' });
  response.end(JSON.stringify(data));
}

async function readBody(request) {
  let body = '';
  for await (const chunk of request) body += chunk;
  try {
    return JSON.parse(body || '{}');
  } catch {
    return null;
  }
}

function checkIn(bookingCode, userId = null) {
  const seat = state.seats.find((item) => item.bookingCode === bookingCode);
  if (!seat || seat.status !== 'reserved') return null;
  const booking = state.bookings.find((item) => item.code === bookingCode);
  if (userId && booking?.userId !== userId) return null;
  seat.status = 'occupied';
  seat.occupiedSince = new Date().toLocaleTimeString('en-US', { hour: 'numeric', minute: '2-digit' });
  if (booking) booking.checkedInAt = new Date().toISOString();
  broadcast();
  return { seat: seat.id, checkedInAt: seat.occupiedSince };
}

const server = http.createServer(async (request, response) => {
  const url = new URL(request.url, `http://${request.headers.host || 'localhost'}`);

  if (url.pathname === '/api/auth/register' && request.method === 'POST') {
    const body = await readBody(request);
    const name = String(body?.name || '').trim();
    const email = String(body?.email || '').trim().toLowerCase();
    const phone = String(body?.phone || '').trim();
    const course = String(body?.course || '').trim();
    const password = String(body?.password || '');
    if (name.length < 2 || name.length > 80 || !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email) || phone.length < 7 || phone.length > 24 || course.length < 2 || course.length > 80 || password.length < 8 || password.length > 128) {
      return sendJson(response, 400, { error: 'Enter your name, valid email, phone, course or class, and a password of at least 8 characters.' });
    }
    if (state.users.some((user) => user.email === email)) return sendJson(response, 409, { error: 'An account already uses that email.' });
    const credentials = hashPassword(password);
    const user = { id: `member-${randomBytes(8).toString('hex')}`, name, email, phone, course, role: 'member', ...credentials };
    state.users.push(user);
    startSession(response, user);
    return sendJson(response, 201, { user: publicUser(user) });
  }

  if (url.pathname === '/api/auth/login' && request.method === 'POST') {
    const body = await readBody(request);
    const email = String(body?.email || '').trim().toLowerCase();
    const role = body?.portal === 'manager' ? 'manager' : 'member';
    const user = state.users.find((entry) => entry.email === email && entry.role === role);
    if (!user || !verifyPassword(String(body?.password || ''), user)) return sendJson(response, 401, { error: 'Email or password did not match.' });
    startSession(response, user);
    return sendJson(response, 200, { user: publicUser(user) });
  }

  if (url.pathname === '/api/auth/logout' && request.method === 'POST') {
    const token = (request.headers.cookie || '').split(';').map((part) => part.trim()).find((part) => part.startsWith('future_library_session='))?.split('=')[1];
    if (token) sessions.delete(token);
    response.setHeader('Set-Cookie', 'future_library_session=; HttpOnly; SameSite=Lax; Path=/; Max-Age=0');
    return sendJson(response, 200, { signedOut: true });
  }

  if (url.pathname === '/api/auth/me' && request.method === 'GET') return sendJson(response, 200, { user: publicUser(currentUser(request)) });

  if (url.pathname === '/api/state' && request.method === 'GET') return sendJson(response, 200, snapshot(currentUser(request)));

  if (url.pathname === '/api/manager/state' && request.method === 'GET') {
    const user = requireRole(request, response, ['manager']);
    if (!user) return;
    return sendJson(response, 200, { ...snapshot(user), orders: state.orders, users: state.users.filter((item) => item.role === 'member').map(publicUser), bookings: state.bookings, rentals: state.rentals });
  }

  if (url.pathname === '/api/manager/books' && request.method === 'POST') {
    const user = requireRole(request, response, ['manager']);
    if (!user) return;
    const body = await readBody(request);
    const title = String(body?.title || '').trim();
    const author = String(body?.author || '').trim();
    const genre = String(body?.genre || '').trim();
    const stock = Number(body?.stock);
    const buyPrice = Number(body?.buyPrice);
    const rentPrice = Number(body?.rentPrice);
    if (title.length < 2 || title.length > 120 || author.length < 2 || author.length > 80 || genre.length < 2 || genre.length > 60 || !Number.isInteger(stock) || stock < 0 || stock > 500 || !Number.isFinite(buyPrice) || buyPrice < 0 || buyPrice > 10000 || !Number.isFinite(rentPrice) || rentPrice < 0 || rentPrice > 10000) {
      return sendJson(response, 400, { error: 'Check the title, author, genre, stock, and prices.' });
    }
    const book = { id: `bk-${randomBytes(8).toString('hex')}`, title, author, genre, isbn: String(body?.isbn || '').replace(/[^0-9Xx]/g, '').slice(0, 13), buyPrice, rentPrice, stock };
    state.books.push(book);
    broadcast();
    return sendJson(response, 201, { book: { ...book, stock: inventoryFor(book) } });
  }

  const managerBookMatch = url.pathname.match(/^\/api\/manager\/books\/([^/]+)$/);
  if (managerBookMatch && request.method === 'PATCH') {
    const user = requireRole(request, response, ['manager']);
    if (!user) return;
    const book = state.books.find((entry) => entry.id === managerBookMatch[1]);
    if (!book) return sendJson(response, 404, { error: 'Book not found.' });
    const body = await readBody(request);
    const stock = Number(body?.stock);
    if (!Number.isInteger(stock) || stock < 0 || stock > 500) return sendJson(response, 400, { error: 'Stock must be a whole number from 0 to 500.' });
    book.stock = stock + state.rentals.filter((rental) => rental.bookId === book.id && !rental.returnedAt).length;
    broadcast();
    return sendJson(response, 200, { book: { ...book, stock: inventoryFor(book) } });
  }

  const managerSeatMatch = url.pathname.match(/^\/api\/manager\/seats\/([^/]+)$/);
  if (managerSeatMatch && request.method === 'PATCH') {
    const user = requireRole(request, response, ['manager']);
    if (!user) return;
    const seat = state.seats.find((entry) => entry.id === managerSeatMatch[1]);
    if (!seat) return sendJson(response, 404, { error: 'Seat not found.' });
    const body = await readBody(request);
    if (!['available', 'occupied'].includes(body?.status)) return sendJson(response, 400, { error: 'Seat status must be available or occupied.' });
    if (seat.bookingCode) {
      const booking = state.bookings.find((item) => item.code === seat.bookingCode);
      if (booking) booking.releasedAt = new Date().toISOString();
    }
    seat.status = body.status;
    seat.bookingCode = null;
    seat.occupiedSince = body.status === 'occupied' ? new Date().toLocaleTimeString('en-US', { hour: 'numeric', minute: '2-digit' }) : null;
    broadcast();
    return sendJson(response, 200, { seat: { id: seat.id, status: seat.status, occupiedSince: seat.occupiedSince } });
  }

  if (url.pathname === '/api/events' && request.method === 'GET') {
    response.writeHead(200, { 'Content-Type': 'text/event-stream', 'Cache-Control': 'no-cache', Connection: 'keep-alive' });
    const user = currentUser(request);
    response.write(`data: ${JSON.stringify(snapshot(user))}\n\n`);
    streamClients.set(response, user);
    request.on('close', () => streamClients.delete(response));
    return;
  }

  if (url.pathname === '/api/bookings' && request.method === 'POST') {
    const user = requireRole(request, response, ['member']);
    if (!user) return;
    const body = await readBody(request);
    const seat = state.seats.find((item) => item.id === body?.seatId);
    const durationHours = Number(body?.durationHours);
    if (!seat || seat.status !== 'available') return sendJson(response, 409, { error: 'That seat is no longer available.' });
    if (!Number.isFinite(durationHours) || durationHours < 1 || durationHours > 8) return sendJson(response, 400, { error: 'Choose a duration from 1 to 8 hours.' });

    const code = randomBytes(4).toString('hex').toUpperCase();
    const now = Date.now();
    const booking = { code, seatId: seat.id, userId: user.id, userName: user.name, durationHours, createdAt: new Date(now).toISOString(), expiresAt: new Date(now + 15 * 60_000).toISOString(), endsAt: new Date(now + durationHours * 3_600_000).toISOString(), checkedInAt: null };
    state.bookings.push(booking);
    seat.status = 'reserved';
    seat.bookingCode = code;
    broadcast();
    return sendJson(response, 201, booking);
  }

  if (url.pathname === '/api/checkin' && request.method === 'GET') {
    const result = checkIn(url.searchParams.get('booking'));
    return result ? sendJson(response, 200, result) : sendJson(response, 404, { error: 'This pass has expired or was already checked in.' });
  }

  if (url.pathname === '/api/checkin' && request.method === 'POST') {
    const user = requireRole(request, response, ['member']);
    if (!user) return;
    const body = await readBody(request);
    const result = checkIn(body?.bookingCode, user.id);
    return result ? sendJson(response, 200, result) : sendJson(response, 404, { error: 'This pass has expired or was already checked in.' });
  }

  if (url.pathname === '/api/checkout' && request.method === 'POST') {
    const user = requireRole(request, response, ['member']);
    if (!user) return;
    const body = await readBody(request);
    const booking = state.bookings.find((item) => item.code === body?.bookingCode);
    const seat = state.seats.find((item) => item.bookingCode === body?.bookingCode);
    if (!booking || booking.userId !== user.id || !seat || seat.status !== 'occupied') return sendJson(response, 404, { error: 'No active checked-in booking found.' });
    seat.status = 'available';
    seat.occupiedSince = null;
    seat.bookingCode = null;
    booking.releasedAt = new Date().toISOString();
    broadcast();
    return sendJson(response, 200, { released: seat.id });
  }

  if (url.pathname === '/api/purchases' && request.method === 'POST') {
    const user = requireRole(request, response, ['member']);
    if (!user) return;
    const body = await readBody(request);
    if (!Array.isArray(body?.items) || body.items.length === 0) return sendJson(response, 400, { error: 'Your bag is empty.' });
    if (body.pickupLocation !== 'main-desk' || !['pay-at-pickup', 'demo-card'].includes(body.paymentMethod)) return sendJson(response, 400, { error: 'Choose the library collection desk and a payment option.' });
    const orderItems = [];
    let total = 0;
    const requestedQuantities = new Map();
    for (const item of body.items) {
      const book = state.books.find((entry) => entry.id === item.bookId);
      const quantity = Number(item.quantity);
      const days = Number(item.days || 7);
      const requested = (requestedQuantities.get(item.bookId) || 0) + quantity;
      requestedQuantities.set(item.bookId, requested);
      if (!book || !Number.isInteger(quantity) || quantity < 1 || requested > inventoryFor(book) || !['buy', 'rent'].includes(item.mode)) {
        return sendJson(response, 409, { error: `${book?.title || 'A book'} is no longer available in that quantity.` });
      }
      if (item.mode === 'rent' && (!Number.isInteger(days) || days < 1 || days > 30)) return sendJson(response, 400, { error: 'Rentals must be between 1 and 30 days.' });
      const unitPrice = item.mode === 'buy' ? book.buyPrice : book.rentPrice * days;
      orderItems.push({ book, quantity, mode: item.mode, days, unitPrice });
      total += unitPrice * quantity;
    }

    const orderCode = randomBytes(3).toString('hex').toUpperCase();
    const now = Date.now();
    for (const item of orderItems) {
      for (let index = 0; index < item.quantity; index += 1) {
        if (item.mode === 'rent') {
          state.rentals.push({ id: randomBytes(5).toString('hex'), userId: user.id, bookId: item.book.id, title: item.book.title, dueAt: new Date(now + item.days * 86_400_000).toISOString(), returnedAt: null });
        } else {
          item.book.stock -= 1;
          state.purchases.push({ userId: user.id, bookId: item.book.id, title: item.book.title, purchasedAt: new Date(now).toISOString(), orderCode });
        }
      }
    }
    const order = { orderCode, userId: user.id, customer: publicUser(user), pickupLocation: 'main-desk', paymentMethod: body.paymentMethod, paymentStatus: body.paymentMethod === 'demo-card' ? 'demo-paid' : 'pay-at-pickup', status: 'ready-for-pickup', total: Number(total.toFixed(2)), createdAt: new Date(now).toISOString(), items: orderItems.map(({ book, quantity, mode, days }) => ({ bookId: book.id, title: book.title, quantity, mode, days: mode === 'rent' ? days : null })) };
    state.orders.push(order);
    broadcast();
    return sendJson(response, 201, order);
  }

  const returnMatch = url.pathname.match(/^\/api\/rentals\/([^/]+)\/return$/);
  if (returnMatch && request.method === 'POST') {
    const user = requireRole(request, response);
    if (!user) return;
    const rental = state.rentals.find((item) => item.id === returnMatch[1] && !item.returnedAt && (item.userId === user.id || user.role === 'manager'));
    if (!rental) return sendJson(response, 404, { error: 'Rental not found.' });
    rental.returnedAt = new Date().toISOString();
    broadcast();
    return sendJson(response, 200, rental);
  }

  if (url.pathname.startsWith('/api/')) return sendJson(response, 404, { error: 'Not found.' });

  const requestedPath = decodeURIComponent(url.pathname === '/' ? '/index.html' : url.pathname);
  const filePath = path.resolve(publicDir, `.${requestedPath}`);
  if (!filePath.startsWith(`${publicDir}${path.sep}`)) return sendJson(response, 403, { error: 'Forbidden.' });
  fs.readFile(filePath, (error, content) => {
    if (error) return sendJson(response, 404, { error: 'Not found.' });
    const types = { '.html': 'text/html; charset=utf-8', '.css': 'text/css; charset=utf-8', '.js': 'text/javascript; charset=utf-8', '.jpg': 'image/jpeg' };
    response.writeHead(200, { 'Content-Type': types[path.extname(filePath)] || 'application/octet-stream' });
    response.end(content);
  });
});

const releaseExpiredReservations = setInterval(() => {
  const now = Date.now();
  let changed = false;
  for (const booking of state.bookings) {
    if (booking.releasedAt) continue;
    const expired = booking.checkedInAt
      ? new Date(booking.endsAt).getTime() <= now
      : new Date(booking.expiresAt).getTime() <= now;
    if (!expired) continue;
    const seat = state.seats.find((item) => item.bookingCode === booking.code);
    if (seat && (seat.status === 'reserved' || seat.status === 'occupied')) {
      seat.status = 'available';
      seat.occupiedSince = null;
      seat.bookingCode = null;
      booking.releasedAt = new Date().toISOString();
      changed = true;
    }
  }
  if (changed) broadcast();
}, 30_000);
releaseExpiredReservations.unref();

if (require.main === module) {
  server.listen(PORT, () => console.log(`future library is ready at http://localhost:${PORT}`));
}

module.exports = { server, snapshot, state };