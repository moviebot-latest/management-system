# future library

A full-stack library prototype with a live reading-room seat map, reservations, QR check-in passes, a searchable buy-or-rent catalog, checkout, rental returns, and a study dashboard.

## Run it

Requires Node.js 18 or newer. There are no npm dependencies to install.

```sh
npm start
```

Then open [http://localhost:3000](http://localhost:3000). To use another port, set `PORT` before starting the server.

Member sign-in and registration live at `/account.html`; the pickup cart is at `/cart.html`; the staff portal is at `/manager.html`. The local demo manager credentials are `manager@futurelibrary.local` / `librarymanager123`. Set `MANAGER_EMAIL` and `MANAGER_PASSWORD` before launch to override them.

## Check it

```sh
npm test
```

The API state, sessions, and accounts are held in memory and reset when the server restarts. Live browser updates use server-sent events. Book covers, photographs, and web fonts are loaded from external services and need an internet connection. Checkout records pay-at-pickup or a no-charge demo-card status; it does not process real payments.