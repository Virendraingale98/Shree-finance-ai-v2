# Google Sheets — 19-Column Schema Setup Guide
## Shree Finance AI v3.3 — F3 Auto-Save

### Step 1 — Create the Sheet
1. Go to [Google Sheets](https://sheets.google.com)
2. Create a new spreadsheet
3. Name it exactly: **`Approved Leads - Shree Finance`**

### Step 2 — Share with Service Account
1. Open `credentials.json` → find `"client_email"` value
2. In your Google Sheet → click **Share**
3. Paste the service account email → set role to **Editor** → click Send

### Step 3 — Run test_db.py
```bash
cd "g:\My Drive\Projects\Shree_Finance_AI_v2"
python test_db.py
```
Type `yes` when asked — this writes the 19 headers automatically.

---

## 19-Column Schema

| # | Column | Source | Description |
|---|--------|--------|-------------|
| 1 | Timestamp | Auto | Date & time of entry |
| 2 | Sender_Phone | Twilio | WhatsApp number |
| 3 | Monthly_Income | NLP / Salary PDF | Net monthly income |
| 4 | Existing_EMI | NLP | Current EMI payments |
| 5 | CIBIL_Score | CIBIL PDF / NLP | Credit score (300-900) |
| 6 | Business_Vintage_Yrs | NLP | Years in business |
| 7 | Loan_Amount | NLP | Requested loan amount |
| 8 | FOIR | Computed | EMI-to-income ratio (%) |
| 9 | Approval_Confidence | ML Model | RandomForest probability |
| 10 | Num_Active_Loans | CIBIL PDF | Open loan count |
| 11 | Overdue_Amount | CIBIL PDF | Outstanding overdue (Rs.) |
| 12 | Max_DPD | CIBIL PDF | Maximum days past due |
| 13 | Enquiries_6m | CIBIL PDF | Credit enquiries in 6 months |
| 14 | Negative_Flags | CIBIL PDF | e.g., SETTLED, WRITTEN OFF |
| 15 | Employer_Name | Salary / Bank PDF | Company name |
| 16 | ITR_Income | ITR PDF | Annual gross income |
| 17 | Doc_Type_Received | Auto | CIBIL+Salary+Bank etc. |
| 18 | Docs_Received | Auto | Yes / No |
| 19 | Reminder_Sent | Manual | Yes / No (update manually) |

---

## Verification Checklist
- [ ] Sheet created with exact name `Approved Leads - Shree Finance`
- [ ] Service account email added as Editor
- [ ] `python test_db.py` runs without errors
- [ ] Row 1 shows all 19 column headers
- [ ] Test row appended and cleaned up
