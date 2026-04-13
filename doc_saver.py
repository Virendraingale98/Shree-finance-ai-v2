"""
=============================================================================
 SHREE FINANCE AI v3.3 — DOCUMENT SAVER MODULE (F3)
 Author  : Virendra Ingale
 Module  : doc_saver.py
 Purpose : F3 — Auto-save parsed data to session + Google Sheets (19 cols)
           + WhatsApp reply builder functions
=============================================================================
"""

import os
import json
from datetime import datetime


# ─────────────────────────────────────────────────────────────
# GOOGLE SHEETS: 19-COLUMN SCHEMA
# ─────────────────────────────────────────────────────────────

SHEET_HEADERS_19 = [
    "Timestamp",           # 1 — auto
    "Sender_Phone",        # 2 — Twilio From
    "Monthly_Income",      # 3 — NLP / Salary PDF
    "Existing_EMI",        # 4 — NLP
    "CIBIL_Score",         # 5 — CIBIL PDF / NLP
    "Business_Vintage_Yrs",# 6 — NLP
    "Loan_Amount",         # 7 — NLP
    "FOIR",                # 8 — computed
    "Approval_Confidence", # 9 — ML model
    "Num_Active_Loans",    # 10 — CIBIL PDF
    "Overdue_Amount",      # 11 — CIBIL PDF
    "Max_DPD",             # 12 — CIBIL PDF
    "Enquiries_6m",        # 13 — CIBIL PDF
    "Negative_Flags",      # 14 — CIBIL PDF
    "Employer_Name",       # 15 — Salary PDF
    "ITR_Income",          # 16 — ITR PDF
    "Doc_Type_Received",   # 17 — auto from router
    "Docs_Received",       # 18 — Yes/No flag
    "Reminder_Sent",       # 19 — Yes/No flag
]


# ─────────────────────────────────────────────────────────────
# SESSION UPDATERS
# ─────────────────────────────────────────────────────────────

def save_cibil_to_session(phone: str, cibil_data: dict,
                           user_sessions: dict) -> dict:
    """
    Merge parsed CIBIL data into the user's session.
    Updates: CIBIL_Score, Num_Active_Loans, Overdue_Amount,
             Max_DPD, Enquiries_6m, Negative_Flags
    Returns updated session dict.
    """
    if phone not in user_sessions:
        user_sessions[phone] = _empty_session()

    sess = user_sessions[phone]

    if cibil_data.get("cibil_score", 0) > 0:
        sess["CIBIL_Score"] = cibil_data["cibil_score"]
    if cibil_data.get("active_loans", 0) > 0:
        sess["Num_Active_Loans"] = cibil_data["active_loans"]

    # Store CIBIL-specific fields (not in ML model but logged to Sheets)
    sess["_cibil_overdue"]   = cibil_data.get("overdue_amount", 0)
    sess["_cibil_max_dpd"]   = cibil_data.get("max_dpd", 0)
    sess["_cibil_enq_6m"]    = cibil_data.get("enquiries_6m", 0)
    sess["_cibil_neg_flags"] = cibil_data.get("negative_flags", [])
    sess["_doc_type"]        = "CIBIL"

    return sess


def save_salary_to_session(phone: str, salary_data: dict,
                            user_sessions: dict) -> dict:
    """
    Merge parsed salary data into session.
    Updates: Monthly_Income, Employer_Name
    """
    if phone not in user_sessions:
        user_sessions[phone] = _empty_session()

    sess = user_sessions[phone]

    net_sal = salary_data.get("net_salary", 0) or \
              salary_data.get("average_monthly_salary", 0)
    if net_sal > 0:
        sess["Monthly_Income"] = net_sal

    sess["_employer_name"] = salary_data.get("employer_name", "Unknown")
    sess["_doc_type"]      = (sess.get("_doc_type", "") + "+Salary").lstrip("+")

    return sess


def save_itr_to_session(phone: str, itr_data: dict,
                         user_sessions: dict) -> dict:
    """Merge parsed ITR data into session."""
    if phone not in user_sessions:
        user_sessions[phone] = _empty_session()

    sess = user_sessions[phone]
    gross = itr_data.get("gross_income", 0)
    if gross > 0:
        # Convert annual ITR income to monthly
        sess["Monthly_Income"] = sess.get("Monthly_Income", 0) or int(gross / 12)
        sess["_itr_income"] = gross

    sess["_doc_type"] = (sess.get("_doc_type", "") + "+ITR").lstrip("+")
    return sess


def save_bank_to_session(phone: str, bank_data: dict,
                          user_sessions: dict) -> dict:
    """Merge parsed bank statement data into session."""
    if phone not in user_sessions:
        user_sessions[phone] = _empty_session()

    sess = user_sessions[phone]
    avg_sal = bank_data.get("average_monthly_salary", 0)
    if avg_sal > 0 and sess.get("Monthly_Income", 0) == 0:
        sess["Monthly_Income"] = avg_sal

    if bank_data.get("employer_name", "Unknown") != "Unknown":
        sess["_employer_name"] = bank_data["employer_name"]

    sess["_doc_type"] = (sess.get("_doc_type", "") + "+Bank").lstrip("+")
    return sess


def _empty_session() -> dict:
    return {
        "Monthly_Income": 0, "Existing_EMI": 0, "CIBIL_Score": 0,
        "Business_Vintage_Yrs": 0, "Loan_Amount": 0,
        "Num_Active_Loans": 0, "Industry_Risk": 2,
        "_cibil_overdue": 0, "_cibil_max_dpd": 0,
        "_cibil_enq_6m": 0, "_cibil_neg_flags": [],
        "_employer_name": "", "_itr_income": 0, "_doc_type": "",
    }


# ─────────────────────────────────────────────────────────────
# GOOGLE SHEETS: 19-COLUMN LOGGER
# ─────────────────────────────────────────────────────────────

def connect_sheets():
    """Connect to Google Sheets using env variable or local credentials.json."""
    try:
        import gspread
        from oauth2client.service_account import ServiceAccountCredentials

        scope = ['https://spreadsheets.google.com/feeds',
                 'https://www.googleapis.com/auth/drive']
        env_creds = os.environ.get("GOOGLE_CREDENTIALS", "")
        if env_creds and len(env_creds) > 10:
            creds_dict = json.loads(env_creds)
        else:
            with open("credentials.json", "r") as f:
                creds_dict = json.loads(f.read())

        creds  = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
        client = gspread.authorize(creds)
        return client.open("Approved Leads - Shree Finance").sheet1
    except Exception as e:
        print(f"[SHEETS ERROR] {e}")
        return None


def ensure_19_col_headers():
    """Ensure Google Sheet has the correct 19-column headers. Run once at startup."""
    sheet = connect_sheets()
    if not sheet:
        print("[SHEETS] Could not connect to set up headers.")
        return False
    try:
        existing = sheet.row_values(1)
        if existing != SHEET_HEADERS_19:
            sheet.insert_row(SHEET_HEADERS_19, 1)
            print("[SHEETS] 19-column headers written successfully.")
        else:
            print("[SHEETS] Headers already correct.")
        return True
    except Exception as e:
        print(f"[SHEETS] Header setup error: {e}")
        return False


def log_19col_to_sheets(phone: str, session: dict, probability: float = 0.0,
                        decision: str = "APPROVED"):
    """
    Write a full 19-column row to Google Sheets.
    Called after ML prediction — logs BOTH approved AND rejected leads.
    """
    sheet = connect_sheets()
    if not sheet:
        print("[SHEETS] Could not connect — lead NOT logged.")
        return

    foir = round(session.get("Existing_EMI", 0) /
                 session["Monthly_Income"], 4) \
           if session.get("Monthly_Income", 0) > 0 else 0

    neg_flags = session.get("_cibil_neg_flags", [])
    neg_flags_str = ", ".join(neg_flags) if neg_flags else "None"

    doc_type = session.get("_doc_type", "Text")
    docs_received = "Yes" if doc_type and doc_type != "Text" else "No"

    row = [
        datetime.now().strftime("%Y-%m-%d %H:%M:%S"),  # 1 Timestamp
        phone,                                          # 2 Phone
        session.get("Monthly_Income", 0),               # 3 Income
        session.get("Existing_EMI", 0),                 # 4 EMI
        session.get("CIBIL_Score", 0),                  # 5 CIBIL
        session.get("Business_Vintage_Yrs", 0),         # 6 Vintage
        session.get("Loan_Amount", 0),                  # 7 Loan Amount
        f"{foir * 100:.1f}%",                           # 8 FOIR
        f"{probability * 100:.1f}% ({decision})",       # 9 Confidence + Decision
        session.get("Num_Active_Loans", 0),             # 10 Active Loans
        session.get("_cibil_overdue", 0),               # 11 Overdue
        session.get("_cibil_max_dpd", 0),               # 12 Max DPD
        session.get("_cibil_enq_6m", 0),                # 13 Enquiries
        neg_flags_str,                                   # 14 Neg Flags
        session.get("_employer_name", ""),               # 15 Employer
        session.get("_itr_income", 0),                  # 16 ITR Income
        doc_type or "Text",                              # 17 Doc Type
        docs_received,                                   # 18 Docs Received
        "No",                                            # 19 Reminder Sent
    ]

    try:
        sheet.append_row(row)
        print(f"[SHEETS] Logged 19-col row for {phone} — {decision}")
    except Exception as e:
        print(f"[SHEETS] Append error: {e}")


# ─────────────────────────────────────────────────────────────
# WHATSAPP REPLY BUILDERS
# ─────────────────────────────────────────────────────────────

def build_cibil_reply(cibil_data: dict) -> str:
    """Build a formatted WhatsApp reply for a parsed CIBIL report."""
    score   = cibil_data.get("cibil_score", 0)
    loans   = cibil_data.get("active_loans", 0)
    overdue = cibil_data.get("overdue_amount", 0)
    dpd     = cibil_data.get("max_dpd", 0)
    enq     = cibil_data.get("enquiries_6m", 0)
    flags   = cibil_data.get("negative_flags", [])

    # Score rating
    if score >= 750:
        score_label = "Excellent 🟢"
    elif score >= 700:
        score_label = "Good 🟡"
    elif score >= 650:
        score_label = "Fair 🟠"
    elif score > 0:
        score_label = "Poor 🔴"
    else:
        score_label = "Not Found ❓"

    neg_line = "✅ No negative flags!" if not flags \
               else f"⚠️ Flags: {', '.join(flags)}"

    next_step = "➡️ Next: Send *Salary Slip* or *Bank Statement*"

    return (
        f"✅ CIBIL Report Read!\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"📊 Score       : {score} — {score_label}\n"
        f"🏦 Active Loans: {loans}\n"
        f"⚠️ Overdue     : Rs.{overdue:,}\n"
        f"📅 Max DPD     : {dpd} days\n"
        f"🔍 Enquiries   : {enq} (last 6m)\n"
        f"{neg_line}\n"
        f"💾 CIBIL data saved.\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"{next_step}"
    )


def build_salary_reply(salary_data: dict) -> str:
    """Build a formatted WhatsApp reply for a parsed salary slip."""
    net    = salary_data.get("net_salary", 0)
    gross  = salary_data.get("gross_salary", 0)
    emp    = salary_data.get("employer_name", "Unknown")
    month  = salary_data.get("pay_month", "")
    name   = salary_data.get("employee_name", "")

    name_line  = f"👤 Employee    : {name}\n" if name else ""
    month_line = f"📅 Pay Month   : {month}\n" if month else ""

    return (
        f"✅ Salary Slip Verified!\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"{name_line}"
        f"🏢 Employer    : {emp}\n"
        f"💰 Net Salary  : Rs.{net:,}\n"
        f"💵 Gross Salary: Rs.{gross:,}\n"
        f"{month_line}"
        f"💾 Income data saved.\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"➡️ Next: Share your *CIBIL Score* or *Business Vintage*"
    )


def build_itr_reply(itr_data: dict) -> str:
    """Build a formatted WhatsApp reply for a parsed ITR."""
    gross  = itr_data.get("gross_income", 0)
    ay     = itr_data.get("assessment_year", "")
    monthly = int(gross / 12) if gross > 0 else 0

    ay_line = f"📅 Asst. Year  : {ay}\n" if ay else ""

    return (
        f"✅ ITR Verified!\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"{ay_line}"
        f"💰 Annual Income : Rs.{gross:,}\n"
        f"📊 Monthly Equiv.: Rs.{monthly:,}\n"
        f"💾 Income data saved.\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"➡️ Next: Send *CIBIL Report* or *Bank Statement*"
    )


def build_bank_reply(bank_data: dict) -> str:
    """Build a formatted WhatsApp reply for a parsed bank statement."""
    avg    = bank_data.get("average_monthly_salary", 0)
    emp    = bank_data.get("employer_name", "Unknown")
    credits = bank_data.get("salary_credits_found", [])

    credits_str = f"Rs.{', Rs.'.join(str(c) for c in credits[:3])}" \
                  if credits else "—"

    return (
        f"✅ Bank Statement Read!\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"🏢 Employer    : {emp}\n"
        f"💰 Avg Salary  : Rs.{avg:,}\n"
        f"📋 Credits     : {credits_str}\n"
        f"💾 Income data saved.\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"➡️ Next: Share your *CIBIL Score* or *Business Years*"
    )


def build_next_step_prompt(session: dict) -> str:
    """
    Build a contextual 'what do we still need?' prompt
    based on what's already in the session.
    """
    missing = []
    if session.get("Monthly_Income", 0) == 0:
        missing.append("💰 Salary / Income")
    if session.get("CIBIL_Score", 0) == 0:
        missing.append("📊 CIBIL Score")
    if session.get("Business_Vintage_Yrs", 0) == 0:
        missing.append("📅 Business Vintage (years)")

    if not missing:
        return "✅ All data collected! Running credit analysis now..."

    missing_str = "\n".join(f"  • {m}" for m in missing)
    return (
        f"📋 Still need:\n{missing_str}\n\n"
        f"Send these as text (e.g., 'CIBIL 720, 4 years business')\n"
        f"or upload the PDF document."
    )


def build_unknown_doc_reply() -> str:
    """Reply when document type cannot be detected."""
    return (
        "⚠️ Document received but type not recognized.\n\n"
        "Please send one of:\n"
        "  📄 CIBIL / Credit Report PDF\n"
        "  📄 Salary Slip PDF\n"
        "  📄 ITR / Form-16 PDF\n"
        "  📄 Bank Statement PDF (last 6 months)\n"
        "  📊 Excel CIBIL (.xlsx)\n\n"
        "Or type your details directly:\n"
        "Example: _Income 60k, CIBIL 720, EMI 10k, 4 years business_"
    )
