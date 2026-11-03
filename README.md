# ONLINE SERVICE HUB

A complete, deployable website for ONLINE SERVICE HUB — ALL ONLINE SERVICES IN ONE PLACE, SINCE 2025.
Branding is black with gold and blue, matching the client logo in `static/logo.jpg`.

## What it does

- **Home, About, Contact, Privacy Policy, Terms & Conditions** — mobile-friendly pages.
- **Customer registration and login with ONLY Full Name + WhatsApp Number** — no email, no customer password.
- **User dashboard** — view Digital Services and Physical Products, place orders, view order details, order tracking and order history.
- **Online ordering with payment at the same time** — an order is NOT complete without payment. Checkout shows manual JazzCash details (number 03297972918, account name Parveen Khalid) and requires a transaction ID.
- **Order flow** — the order appears in the Admin Dashboard immediately. The customer gets an in-account Order Confirmation. The admin verifies the payment in Admin → Orders & Payments; only then does the customer's tracking advance to "Payment verified".
- **Admin Dashboard (complete control)** — PIN-protected. Add, edit and delete Digital Services and Physical Products (with prices), manage customers, orders, payments, reviews/ratings, and site settings. Customers cannot change admin-managed content; admin routes require the admin session.
- **WhatsApp contact/support** — support contact Hammad, WhatsApp 03704984676, shown as a WhatsApp button on every page, on the Contact page and in the footer.
- **Reviews & ratings** — logged-in customers can review an item; reviews show only after admin approval in Admin → Reviews.
- **Catalog starts empty** — no services or prices were provided by the client, and the owner adds them from Admin → Services & Products. No priced items are invented as the client's real catalog. Test items created during local testing were removed; the shipped database starts empty.

## What this is NOT — read plainly

- **No real payment gateway.** Payment is manual JazzCash + transaction ID + admin verification. Money is not collected automatically by this app.
- **No real email sending.** "Notifications" are in-account confirmations in the customer's dashboard plus the admin notification flow, because registration collects no email address and no mail service is connected.
- **No automatic payment confirmation.** An order shows as "payment pending" until the admin verifies it.

## Admin login

- First PIN: `admin123`
- Change it immediately after first login in Admin → Site Settings → New Admin PIN.
- Do not share the PIN publicly. If you change it and forget it, you must reset the `admin_pin_hash` setting in the SQLite database (see RENDER_DEPLOY.txt).

## Run locally

```bash
cd online-service-hub
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python app.py
```

Then open http://127.0.0.1:5000

Environment variables (optional):

- `OSH_DB` — path to the SQLite file (default: `data.db` in the app folder).
- `OSH_SECRET` — Flask session secret. Set a long random value in production.
- `PORT` — port to listen on (Render sets this automatically).

## Deploy for free

See `RENDER_DEPLOY.txt` for exact Render free-tier steps, including the important warning that SQLite on free Render without a persistent disk can reset on redeploy/restart.
