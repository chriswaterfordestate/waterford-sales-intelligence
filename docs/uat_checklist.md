# Waterford Sales Intelligence — UAT Checklist

**Version:** Sprint 6 Release Candidate  
**For:** Chris Wicht (NSM) — non-technical acceptance test  
**Estimated time:** 25–35 minutes

Perform these checks after the application is deployed. For each item, note ✓ Pass or ✗ Fail.

---

## 1. Authentication

| # | Action | Expected result |
|---|--------|----------------|
| 1.1 | Open the application URL in a browser (not logged in) | Login screen appears. No application data is visible. |
| 1.2 | Try opening `/api/commercial/dashboard` directly in the browser | Returns an error (401 Unauthorized). Data is protected. |
| 1.3 | Log in with your Waterford credentials | You are taken to the home dashboard. |

---

## 2. FY2027 Dashboard

| # | Action | Expected result |
|---|--------|----------------|
| 2.1 | Open the Home / Dashboard page | FY2027 Jul–Aug commercial performance displays. Bottles and revenue visible. |
| 2.2 | Check the YoY comparison label | Shows "FY2027 Jul–Aug vs FY2026 Jul–Aug" — not a full-year comparison. |
| 2.3 | Check the distributor sell-in section | Shows separately below commercial totals. Not included in the commercial bottle count. |

---

## 3. Import Centre

| # | Action | Expected result |
|---|--------|----------------|
| 3.1 | Navigate to Imports | Page loads with a drag-and-drop upload area and a list of recent imports. |
| 3.2 | Upload the FY2027 ERP file (`17_august.csv`) | File is recognised as ERP_EXPORT. Import result shows mapped/excluded/pending counts. |
| 3.3 | Upload the same file again immediately | Result shows "already imported" (DUPLICATE_DETECTED). Row counts are unchanged. |
| 3.4 | Upload a file with an unclear format (e.g. a random CSV) | Application shows four source choices. No automatic import occurs. |
| 3.5 | Select "ERP / EzyWine CSV export" from the source choices | Import runs using the selected connector. |

---

## 4. Commercial Queue

| # | Action | Expected result |
|---|--------|----------------|
| 4.1 | Navigate to Commercial Queue | List of unresolved commercial debtors appears, sorted by revenue (highest first). |
| 4.2 | Confirm that Tasting Room / Wine Club / Export debtors are NOT in the list | Only commercial accounts appear. DTC and export are excluded. |
| 4.3 | Click on a debtor (e.g. Woolworths) | Detail panel opens on the right. Revenue, bottles, and period information visible. |
| 4.4 | Search for "Woolworths" in the canonical client search | "Woolworths Food" appears as a result. |
| 4.5 | Select "Woolworths Food" | Mapping confirmed. Debtor disappears from the queue. Dashboard updates. |

---

## 5. Client 360 — Sales Intelligence

| # | Action | Expected result |
|---|--------|----------------|
| 5.1 | Search for "Van Riebeeck Liquors" | Client appears in search results. |
| 5.2 | Open Van Riebeeck Liquors | FY2027 and FY2026 equivalent performance visible. YoY percentage displayed. |
| 5.3 | Check product mix | Shows which Waterford products this client buys. |
| 5.4 | Check "Not currently buying" section | Shows Waterford products this client has not ordered recently. |

---

## 6. Client 360 — CRM (Log Visit)

| # | Action | Expected result |
|---|--------|----------------|
| 6.1 | Click "Log Visit" on Van Riebeeck Liquors | Modal opens. Client is pre-filled. Date defaults to today. |
| 6.2 | Select a rep, choose outcome "Positive", and type a note | Fields accept input. No required-field errors yet. |
| 6.3 | Tick "Add a next action". Set type to "Tasting" and a due date next week | Tasting action fields appear. |
| 6.4 | Tick "Request support". Set type to "Samples" | Support request fields appear. |
| 6.5 | Click "Save visit" | Modal closes. Last Visit updates on the Client 360 page. |
| 6.6 | On the confirmation screen, click "Download .ics (Add to Outlook)" | A `.ics` file downloads. Open it — it shows the client name, action type, and due date. |

---

## 7. Activity Timeline

| # | Action | Expected result |
|---|--------|----------------|
| 7.1 | Scroll down on the Client 360 page after logging the visit | The visit appears in the activity timeline with date, rep name, outcome, and note. |
| 7.2 | Open the Relationship panel | "Last visit" shows today's date and the outcome chosen. |

---

## 8. My Day (Rep View)

| # | Action | Expected result |
|---|--------|----------------|
| 8.1 | Navigate to My Day | View loads. Select Koliswa Jayiya from the rep dropdown. |
| 8.2 | Check "Requires action" | Shows any overdue or due-today actions for Koliswa. |
| 8.3 | Check "Next 7 days" | Shows the Tasting action created in step 6.3. |
| 8.4 | Click on a client in the list | Opens that client's Client 360 directly. |

---

## 9. Manager View

| # | Action | Expected result |
|---|--------|----------------|
| 9.1 | Navigate to Manager View | Team activity, overdue actions, support requests, and declining accounts visible. |
| 9.2 | Check support requests | The "Samples" request created in step 6.4 appears here. |
| 9.3 | Check declining accounts | Accounts down more than 20% YoY are listed with the rep name and YoY %. |

---

## 10. Data Integrity

| # | Action | Expected result |
|---|--------|----------------|
| 10.1 | On any Client 360, check the Source breakdown | Direct ERP and NGF sell-through shown separately. Never combined. |
| 10.2 | Navigate to Dashboard and note commercial bottle count | Does NOT include distributor sell-in (shown separately in the blue notice below). |
| 10.3 | Check that YoY compares the same months | "FY2027 Jul–Aug vs FY2026 Jul–Aug" — not full FY2026. |

---

**Acceptance signature:** _________________ Date: _________
