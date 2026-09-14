# Waterford Sales Intelligence — Admin Guide

**Audience:** Chris Wicht, NSM (non-technical)  
**Version:** Sprint 6

This guide explains how to run the application day-to-day without SQL, code, or a command line.

---

## Where everything lives

| What | Where |
|------|-------|
| Application (web) | Your Render frontend URL (e.g. `https://waterford-si-frontend.onrender.com`) |
| Backend API | Your Render backend URL (e.g. `https://waterford-si-api.onrender.com`) |
| Database | Render → your team → waterford-si-db |
| Environment variables | Render dashboard → waterford-si-api → Environment |
| Backups | Render PostgreSQL → automatic daily backups, 7-day retention |
| Authentication / users | Clerk dashboard → [dashboard.clerk.com](https://dashboard.clerk.com) |

---

## Critical one-time setup: Clerk session token

**This step is required before any user can receive their correct role.**

Without it, all users default to REP regardless of what Public Metadata you set.

1. Go to [dashboard.clerk.com](https://dashboard.clerk.com) → your Waterford application
2. Click **Configure** → **Sessions** → **Customize session token**
3. Add the following JSON:
   ```json
   {
     "role": "{{user.public_metadata.role}}"
   }
   ```
4. Click **Save**

**Why this is required:** The backend reads the role from the Clerk JWT (JSON Web Token). Clerk does not automatically include user Public Metadata in the session token — you must configure it explicitly. The backend reads the top-level `role` claim; without the custom claim, it safely defaults all users to REP.

---

## Adding a new user

No SQL, no API calls, no UUID lookup required. The process is entirely through the Clerk dashboard and the Waterford web application.

### Step 1 — Invite the person in Clerk

1. Go to [dashboard.clerk.com](https://dashboard.clerk.com) → **Users** → **Invite**
2. Enter their email address. They receive an invitation and set their own password.

### Step 2 — Set their role in Clerk

1. In Clerk → **Users**, click the person's name
2. Click **Public Metadata** (right-hand panel)
3. Enter their role as JSON:
   - `{"role": "ADMIN"}` — for you (Chris) and any other administrators
   - `{"role": "MANAGER"}` — for regional managers who need team visibility
   - `{"role": "REP"}` — for sales reps (this is the safe default if unset)
4. Save

### Step 3 — Copy their Clerk User ID

On the same Clerk user page, copy the **User ID** — it starts with `user_` (e.g. `user_2abc1234xyz`).

### Step 4 — Map them to a Waterford rep

1. Open the Waterford Sales Intelligence web application
2. Go to **Users / Access** in the left sidebar (admin-only)
3. Enter the Clerk User ID, their email address, and select their Waterford rep from the dropdown
4. Click **Save mapping**

After this, when that person logs in, their My Day loads automatically with their accounts. They do not need to select themselves.

---

## Normal tasks

### Importing a new sales file

1. Open the application → **Imports** (left sidebar)
2. Drag your file onto the upload area, or click to browse
3. The application automatically identifies the format (ERP CSV, NGF Monthly, Distriliq, etc.)
4. If it cannot identify the file, you are shown four format choices — select the correct one
5. The import result shows: rows processed, clients resolved, rows pending review

Supported formats: ERP/EzyWine CSV · NGF SalesOut Excel · NGF Monthly Waterford Report · Distriliq CPT Client Report

Duplicate files are automatically rejected.

---

### Resolving unknown clients after import

1. Go to **Commercial Queue**
2. The list shows unresolved commercial debtors, highest-revenue first
3. Click a debtor to open the resolution panel on the right
4. Search for the canonical client name (e.g. "Woolworths")
5. Select the match — the application registers the alias and retroactively processes all historical rows

The debtor disappears from the queue. Dashboard updates immediately.

---

### Logging a visit

1. Go to **Clients** → search for the client
2. Open the client
3. Click **Log Visit** (top right)
4. The form pre-fills the client, today's date, and your rep identity
5. Select outcome and type your note
6. Optionally tick "Add a next action" or "Request support"
7. Save

To download an Outlook calendar event for the next action, click "Download .ics (Add to Outlook)" after saving.

---

### Reviewing support requests

Go to **Manager View** → scroll to "Support requests" to see all outstanding requests.

---

## Infrastructure tasks

### Checking the application is running

Render dashboard → your team → waterford-si-api → status should show **Live**.

Health check: `https://waterford-si-api.onrender.com/api/health` returns `{"status":"ok"}`.

### Viewing logs

Render dashboard → waterford-si-api → **Logs**. Share with your developer if something goes wrong.

### Restoring from backup after a bad import

Render PostgreSQL → your database → **Backups** → select a backup → **Restore**.

### Environment variables

Render dashboard → waterford-si-api → **Environment** → Edit. Trigger a manual redeploy after any change.

---

## Known product gaps (require developer involvement)

| Task | Current method |
|------|---------------|
| Add a new rep record | SQL (one-time setup per rep) |
| Change a rep's territory | SQL |
| Edit FY targets | SQL |

---

## Costs (indicative, Render pricing as of Sep 2026)

| Service | Plan | Approximate monthly cost |
|---------|------|--------------------------|
| Backend (web service) | Starter | ~$7 USD |
| Frontend (static site) | Free | $0 |
| PostgreSQL | Starter | ~$7 USD |
| Clerk (≤10,000 monthly active users) | Free | $0 |
| **Total** | | **~$14 USD/month** |

Check [render.com/pricing](https://render.com/pricing) for current prices.

---

*Last updated: Sprint 6 — September 2026*
