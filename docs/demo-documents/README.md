# Demo documents

Fictional company policies and one SOP update for showing the **Documents** page and the assistant. They use the same
roles, escalation levels (L1/L2/L3), 7-day resolution target and £100,000 revenue-at-risk threshold as the built-in
SOPs and the Executive overview, so answers line up across the app.

| File | Type when uploaded | What it covers |
|---|---|---|
| `Loss-Prevention-and-Shrinkage-Policy.pdf` | Reference | Principles, roles, L1–L3 response times, 7-day SLA and 95% target, police and HR referrals, accuracy and shrink targets, retention |
| `Goods-In-and-Receiving-Standard.pdf` | Reference | Scanning every carton, pack-size checks, 48-hour claim window, 5% booked-vs-scanned recount rule |
| `Stocktake-and-Cycle-Count-Procedure.docx` | Reference | Count frequency, blind counts, ±1 unit or 2% tolerance, reason codes, adjustment approval limits |
| `Till-Controls-Voids-and-Refunds-Policy.docx` | Reference | £20 void control, keyed entries, overrides, £250 no-receipt refund limit, daily exception report |
| `CCTV-and-Evidence-Handling-Guideline.md` | Reference | When CCTV may be reviewed, who may view it, 30-day retention, chain of custody |
| `SOP-scan-fraud-v2.md` | **Live SOP** | Version 2.0 of the till-fraud SOP: adds the exception-report review, the £20 void and £250 refund controls and a CCTV step |

## Demo script (about 3 minutes)

1. **Analyst → Documents.** Point out the sources the assistant already reads (guide, glossary, 11 built-in SOPs).
2. **Upload the five reference documents** (drag them in together, type *Detect*). Each shows its passage count; PDFs are
   cut by section and cited as "Page 2 › 7. Police and HR referrals".
3. **Test what the assistant finds:**
   - "who approves a refund without a receipt over 250 pounds" → Till Controls policy, *Refunds*
   - "deadline to claim a short delivery from the distribution centre" → Goods-In standard, *4. Discrepancies*
   - "when do we report theft to the police" → Loss Prevention policy, *7. Police and HR referrals*
   - "who can approve a stock adjustment of 700 pounds": with keywords only this misses; with the embedding model set
     in Settings it finds the Stocktake procedure's *Approval limits* (labelled "keywords + meaning"). Good moment to
     explain hybrid search.
4. **Live SOP update.** Open a till-fraud alert (Act → Alerts, type *Till / scan fraud*) and note the SOP is version 1.0
   with 5 steps. Upload `SOP-scan-fraud-v2.md`: the library says *Replaces the built-in SOP scan-fraud*. Reopen the
   alert: the checklist is version 2.0 with the new exception-report and CCTV steps. Delete the upload to go back.
5. **Ask the assistant** (chat): "A till-fraud alert came in at Store 018. What do our policies say the store manager
   should check first, and what are the refund limits?" It should quote the SOP and the Till Controls policy by name.

The PDFs and Word files have real text layers (no OCR needed).
