"""
=============================================================================
 SHREE FINANCE AI v3.3 — PDF PARSERS MODULE (F1 + F2)
 Author  : Virendra Ingale
 Module  : pdf_parsers.py
 Purpose : Smart document type detection + multi-format parsing
           F1 — CIBIL PDF parser (score, loans, DPD, enquiries, flags)
           F2 — Multi-doc router (CIBIL / Salary / ITR / Bank / Excel)
=============================================================================
"""

import io
import re
import os
import requests

# ── Optional imports with graceful fallback ──
try:
    import pikepdf
    import pdfplumber
    PDF_SUPPORT = True
except ImportError:
    PDF_SUPPORT = False
    print("[WARN] pikepdf/pdfplumber not installed. PDF parsing disabled.")

try:
    import openpyxl
    EXCEL_SUPPORT = True
except ImportError:
    EXCEL_SUPPORT = False
    print("[WARN] openpyxl not installed. Excel CIBIL parsing disabled.")


# ─────────────────────────────────────────────────────────────
# HELPER: Download PDF from Twilio URL
# ─────────────────────────────────────────────────────────────

def download_pdf(url: str) -> bytes:
    """Download a file from a Twilio media URL using Basic Auth."""
    twilio_sid   = os.environ.get("TWILIO_ACCOUNT_SID", "")
    twilio_token = os.environ.get("TWILIO_AUTH_TOKEN", "")
    try:
        resp = requests.get(url, auth=(twilio_sid, twilio_token), timeout=20)
        resp.raise_for_status()
        return resp.content
    except Exception as e:
        raise RuntimeError(f"Download failed: {e}")


# ─────────────────────────────────────────────────────────────
# HELPER: Unlock Password-Protected PDF
# ─────────────────────────────────────────────────────────────

BANK_PASSWORD_GENERATORS = {
    'HDFC' : lambda n, d: f"{n[:4].lower()}{d[2:4]}{d[0:2]}",
    'SBI'  : lambda n, d: f"{n[:4].upper()}{d[0:2]}{d[2:4]}",
    'ICICI': lambda n, d: f"{n[:3].upper()}{d[0:2]}{d[3:5]}{d[6:]}",
    'AXIS' : lambda n, d: f"{n[:4].lower()}{d[6:]}",
}

def generate_passwords(name: str, dob: str = "01011990", phone: str = "0000") -> list:
    """Generate common Indian bank PDF passwords to try auto-unlock."""
    first = name.strip().split()[0] if name else "user"
    pwds  = [phone[-4:], dob.replace('/', ''), dob.replace('-', ''), ""]
    for fn in BANK_PASSWORD_GENERATORS.values():
        try:
            pwds.append(fn(first, dob))
        except Exception:
            pass
    return list(set(filter(None, pwds)))

def unlock_pdf(pdf_bytes: bytes, name: str = "client",
               dob: str = "01011990", phone: str = "9999") -> bytes:
    """Try to unlock PDF. Returns unlocked bytes or raises RuntimeError."""
    if not PDF_SUPPORT:
        raise RuntimeError("pikepdf not installed.")
    try:
        with pikepdf.open(io.BytesIO(pdf_bytes)):
            return pdf_bytes  # Already unlocked
    except pikepdf.PasswordError:
        for pwd in generate_passwords(name, dob, phone):
            try:
                with pikepdf.open(io.BytesIO(pdf_bytes), password=pwd) as p:
                    buf = io.BytesIO()
                    p.save(buf)
                    return buf.getvalue()
            except Exception:
                continue
    raise RuntimeError("PDF locked. Please send the password separately.")


# ─────────────────────────────────────────────────────────────
# F2: DOCUMENT TYPE DETECTOR
# ─────────────────────────────────────────────────────────────

CIBIL_KEYWORDS   = ['cibil', 'credit score', 'credit information', 'transunion',
                     'experian', 'crif', 'credit report', 'dpd', 'days past due',
                     'credit enquir', 'overdue', 'credit card outstanding']
SALARY_KEYWORDS  = ['salary slip', 'pay slip', 'payslip', 'net pay', 'gross salary',
                     'basic pay', 'allowance', 'deduction', 'pf deduction',
                     'employee name', 'employee id', 'month', 'payroll']
ITR_KEYWORDS     = ['income tax return', 'itr', 'form 16', 'assessment year',
                     'gross total income', 'taxable income', 'tax paid',
                     'pan number', 'tds', 'income from salary']
BANK_KEYWORDS    = ['bank statement', 'account statement', 'opening balance',
                     'closing balance', 'transaction', 'credit', 'debit',
                     'neft', 'imps', 'upi', 'cheque']

def detect_doc_type(text: str) -> str:
    """
    Classify document type from extracted PDF text.
    Returns: 'cibil' | 'salary' | 'itr' | 'bank' | 'unknown'
    """
    text_lower = text.lower()

    def score(keywords):
        return sum(1 for kw in keywords if kw in text_lower)

    scores = {
        'cibil'  : score(CIBIL_KEYWORDS),
        'salary' : score(SALARY_KEYWORDS),
        'itr'    : score(ITR_KEYWORDS),
        'bank'   : score(BANK_KEYWORDS),
    }
    best = max(scores, key=scores.get)
    return best if scores[best] >= 2 else 'unknown'


# ─────────────────────────────────────────────────────────────
# F1: CIBIL PDF PARSER
# ─────────────────────────────────────────────────────────────

def parse_cibil(pdf_bytes: bytes) -> dict:
    """
    Parse CIBIL Credit Report PDF.
    Extracts: score, active_loans, overdue_amount, max_dpd,
              enquiries_6m, negative_flags
    """
    if not PDF_SUPPORT:
        return {"error": "PDF parsing not available."}

    full_text = ""
    try:
        with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
            for page in pdf.pages[:8]:  # CIBIL reports can be long
                full_text += (page.extract_text() or "") + "\n"
    except Exception as e:
        return {"error": f"PDF read error: {e}"}

    result = {
        "doc_type"       : "cibil",
        "cibil_score"    : 0,
        "active_loans"   : 0,
        "overdue_amount" : 0,
        "max_dpd"        : 0,
        "enquiries_6m"   : 0,
        "negative_flags" : [],
        "raw_text_len"   : len(full_text),
    }

    # ── CIBIL Score ──
    score_patterns = [
        r'(?:cibil\s*score|credit\s*score|your\s*score)[^\d]*(\d{3})',
        r'\b(7\d{2}|[89]\d{2}|[3-6]\d{2})\b(?=\s*(?:score|points|rating))',
        r'score[^\d]*(\d{3})',
    ]
    for pat in score_patterns:
        m = re.search(pat, full_text, re.IGNORECASE)
        if m:
            val = int(m.group(1))
            if 300 <= val <= 900:
                result["cibil_score"] = val
                break

    # ── Active / Open Loan Accounts ──
    loan_patterns = [
        r'(?:active|open)\s*(?:loan|account)[s]?[^\d]*(\d{1,2})',
        r'no\.?\s*of\s*(?:active|open)\s*account[s]?[^\d]*(\d{1,2})',
        r'total\s*accounts?[^\d]*(\d{1,2})',
    ]
    for pat in loan_patterns:
        m = re.search(pat, full_text, re.IGNORECASE)
        if m:
            result["active_loans"] = int(m.group(1))
            break

    # ── Overdue Amount ──
    overdue_patterns = [
        r'(?:total\s*)?overdue[^\d]*([\d,]+)',
        r'amount\s*overdue[^\d]*([\d,]+)',
    ]
    for pat in overdue_patterns:
        m = re.search(pat, full_text, re.IGNORECASE)
        if m:
            result["overdue_amount"] = int(m.group(1).replace(',', ''))
            break

    # ── Max DPD (Days Past Due) ──
    dpd_patterns = [
        r'(?:max|maximum)\s*dpd[^\d]*(\d{1,3})',
        r'days\s*past\s*due[^\d]*(\d{1,3})',
        r'dpd[^\d]*(\d{1,3})',
    ]
    for pat in dpd_patterns:
        m = re.search(pat, full_text, re.IGNORECASE)
        if m:
            result["max_dpd"] = int(m.group(1))
            break

    # ── Credit Enquiries in last 6 months ──
    enq_patterns = [
        r'(?:enquir(?:y|ies)|inquiry|inquiries)[^\d]*(?:last\s*6[^\d]*)(\d{1,2})',
        r'(\d{1,2})\s*(?:enquir(?:y|ies)|inquiry)\s*(?:in\s*)?(?:last\s*)?6\s*month',
        r'no\.?\s*of\s*enquir(?:y|ies)[^\d]*(\d{1,2})',
    ]
    for pat in enq_patterns:
        m = re.search(pat, full_text, re.IGNORECASE)
        if m:
            result["enquiries_6m"] = int(m.group(1))
            break

    # ── Negative Flags ──
    negative_keywords = {
        'SETTLED'    : r'\bsettled\b',
        'WRITTEN OFF': r'\bwritten[\s-]?off\b',
        'SUIT FILED' : r'\bsuit\s*filed\b',
        'WILFUL DEFAULT': r'\bwilful\s*default\b',
        'DOUBTFUL'   : r'\bdoubtful\b',
    }
    flags = []
    for label, pat in negative_keywords.items():
        if re.search(pat, full_text, re.IGNORECASE):
            flags.append(label)
    result["negative_flags"] = flags

    return result


# ─────────────────────────────────────────────────────────────
# F2: SALARY SLIP PARSER
# ─────────────────────────────────────────────────────────────

def parse_salary_slip(pdf_bytes: bytes) -> dict:
    """Parse Salary Slip PDF — extracts net salary, employer, month."""
    if not PDF_SUPPORT:
        return {"error": "PDF parsing not available."}

    full_text = ""
    try:
        with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
            for page in pdf.pages[:3]:
                full_text += (page.extract_text() or "") + "\n"
    except Exception as e:
        return {"error": f"PDF read error: {e}"}

    result = {
        "doc_type"         : "salary",
        "net_salary"       : 0,
        "gross_salary"     : 0,
        "employer_name"    : "Unknown",
        "pay_month"        : "",
        "employee_name"    : "",
    }

    # ── Net Salary ──
    net_patterns = [
        r'net\s*(?:pay|salary|take\s*home)[^\d]*([\d,]+)',
        r'net\s*amount[^\d]*([\d,]+)',
        r'take\s*home[^\d]*([\d,]+)',
    ]
    for pat in net_patterns:
        m = re.search(pat, full_text, re.IGNORECASE)
        if m:
            val = int(m.group(1).replace(',', ''))
            if 5000 < val < 2000000:
                result["net_salary"] = val
                break

    # ── Gross Salary ──
    gross_patterns = [
        r'gross\s*(?:salary|pay|earnings?)[^\d]*([\d,]+)',
        r'total\s*earnings?[^\d]*([\d,]+)',
    ]
    for pat in gross_patterns:
        m = re.search(pat, full_text, re.IGNORECASE)
        if m:
            val = int(m.group(1).replace(',', ''))
            if 5000 < val < 2000000:
                result["gross_salary"] = val
                break

    # ── Employer Name ──
    emp_patterns = [
        r'(?:company|employer|organisation|organization)\s*(?:name)?[:\s]+([A-Za-z][A-Za-z\s&.]+)',
        r'^([A-Z][A-Z\s&.]{4,40})\s*(?:pvt|ltd|limited|private|llp)',
    ]
    for pat in emp_patterns:
        m = re.search(pat, full_text, re.IGNORECASE | re.MULTILINE)
        if m:
            result["employer_name"] = m.group(1).strip()[:50]
            break

    # ── Pay Month ──
    month_m = re.search(
        r'(?:pay\s*period|month|for\s*the\s*month)\s*(?:of)?\s*'
        r'(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\s*(\d{2,4})',
        full_text, re.IGNORECASE
    )
    if month_m:
        result["pay_month"] = f"{month_m.group(1)} {month_m.group(2)}"

    # ── Employee Name ──
    name_m = re.search(
        r'(?:employee\s*name|name\s*of\s*employee)[:\s]+([A-Za-z\s]+)',
        full_text, re.IGNORECASE
    )
    if name_m:
        result["employee_name"] = name_m.group(1).strip()[:40]

    # Use gross if net not found
    if result["net_salary"] == 0 and result["gross_salary"] > 0:
        result["net_salary"] = result["gross_salary"]

    return result


# ─────────────────────────────────────────────────────────────
# F2: ITR PARSER
# ─────────────────────────────────────────────────────────────

def parse_itr(pdf_bytes: bytes) -> dict:
    """Parse ITR / Form-16 PDF — extracts gross income, assessment year."""
    if not PDF_SUPPORT:
        return {"error": "PDF parsing not available."}

    full_text = ""
    try:
        with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
            for page in pdf.pages[:5]:
                full_text += (page.extract_text() or "") + "\n"
    except Exception as e:
        return {"error": f"PDF read error: {e}"}

    result = {
        "doc_type"         : "itr",
        "gross_income"     : 0,
        "taxable_income"   : 0,
        "assessment_year"  : "",
    }

    # ── Gross Total Income ──
    gross_patterns = [
        r'gross\s*total\s*income[^\d]*([\d,]+)',
        r'total\s*income[^\d]*([\d,]+)',
        r'income\s*chargeable[^\d]*([\d,]+)',
    ]
    for pat in gross_patterns:
        m = re.search(pat, full_text, re.IGNORECASE)
        if m:
            val = int(m.group(1).replace(',', ''))
            if val > 10000:
                result["gross_income"] = val
                break

    # ── Assessment Year ──
    ay_m = re.search(r'assessment\s*year[:\s]*(\d{4}[-–]\d{2,4})', full_text, re.IGNORECASE)
    if ay_m:
        result["assessment_year"] = ay_m.group(1)

    return result


# ─────────────────────────────────────────────────────────────
# F2: BANK STATEMENT PARSER (kept from v3.0, improved)
# ─────────────────────────────────────────────────────────────

def parse_bank_statement(pdf_bytes: bytes) -> dict:
    """
    Parse Bank Statement PDF.
    IMPORTANT: Only extracts SALARY credits — not UPI, not transfers, not refunds.
    Strategy: Match lines that contain salary keywords (SAL/SALARY/PAYROLL/WAGES)
              alongside a credit amount. Ignores all other credit transactions.
    """
    if not PDF_SUPPORT:
        return {"error": "PDF parsing not available."}

    full_text = ""
    try:
        with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
            for page in pdf.pages[:6]:
                full_text += (page.extract_text() or "") + "\n"
    except Exception as e:
        return {"error": f"PDF read error: {e}"}

    salary_amounts = []
    employer       = "Unknown"

    # ── STEP 1: Extract line-by-line to isolate transactions ──
    lines = full_text.split("\n")

    # Salary-specific keywords that MUST appear in the SAME line as the credit amount
    # This prevents picking up random UPI/NEFT credits that are not salary
    SALARY_LINE_KEYWORDS = [
        "salary", "sal ", "sal/", "/sal",
        "payroll", "pay roll",
        "wages", "wage",
        "emolument",
        "stipend",
        "monthly pay",
        "staff pay",
    ]

    for line in lines:
        line_lower = line.lower()

        # Check if this line is a salary credit
        is_salary_line = any(kw in line_lower for kw in SALARY_LINE_KEYWORDS)
        if not is_salary_line:
            continue

        # Extract the amount from this salary line
        # Bank statement amounts are typically 5-8 digits: 10000 to 9,99,999
        amounts_in_line = re.findall(r'[\d,]{5,10}', line)
        for amt_str in amounts_in_line:
            try:
                val = int(amt_str.replace(",", ""))
                # Valid monthly salary range: Rs.8,000 to Rs.5,00,000
                if 8000 < val < 500000:
                    salary_amounts.append(val)
                    break  # Take only the first valid amount per salary line
            except ValueError:
                continue

    # ── STEP 2: Deduplicate — same salary credited twice on same page ──
    # Keep only unique amounts (within 5% of each other = same salary month)
    unique_salaries = []
    for amt in salary_amounts:
        already_seen = any(abs(amt - s) / max(s, 1) < 0.05 for s in unique_salaries)
        if not already_seen:
            unique_salaries.append(amt)

    # ── STEP 3: Average the unique monthly salary credits ──
    avg_salary = int(sum(unique_salaries) / len(unique_salaries)) if unique_salaries else 0

    # ── STEP 4: Try to find employer from NEFT/salary description ──
    # Looks for patterns like "NEFT-EMPLOYER NAME-SAL" or "FROM: XYZ LTD"
    employer_patterns = [
        r'(?:salary|sal)[^\n]*?(?:from|by|neft)[^\n]*?([A-Z][A-Z\s&.]{4,35})',
        r'neft[^\n]*?([A-Z][A-Z\s&.]{4,35})[^\n]*?(?:sal|salary)',
        r'(?:FROM|BY)\s*[:\-]?\s*([A-Z][A-Z\s&.]{4,35})',
    ]
    for pat in employer_patterns:
        m = re.search(pat, full_text, re.IGNORECASE)
        if m:
            name = m.group(1).strip().rstrip("0123456789 /-")
            if len(name) > 3:
                employer = name[:50]
                break

    return {
        "doc_type"              : "bank",
        "average_monthly_salary": avg_salary,
        "employer_name"         : employer,
        "salary_credits_found"  : unique_salaries,
        "months_detected"       : len(unique_salaries),
    }


# ─────────────────────────────────────────────────────────────
# F2: EXCEL CIBIL PARSER (.xlsx)
# ─────────────────────────────────────────────────────────────

def parse_excel_cibil(xlsx_bytes: bytes) -> dict:
    """Parse Excel (.xlsx) CIBIL report — extracts score and key fields."""
    if not EXCEL_SUPPORT:
        return {"error": "openpyxl not installed."}

    result = {
        "doc_type"     : "cibil",
        "cibil_score"  : 0,
        "active_loans" : 0,
        "overdue_amount": 0,
        "source"       : "excel",
    }

    try:
        wb = openpyxl.load_workbook(io.BytesIO(xlsx_bytes), read_only=True, data_only=True)
        for sheet in wb.worksheets:
            for row in sheet.iter_rows(values_only=True):
                for i, cell in enumerate(row):
                    if cell is None:
                        continue
                    cell_str = str(cell).lower()
                    # Look for score in adjacent cell
                    if 'score' in cell_str and i + 1 < len(row):
                        try:
                            val = int(float(str(row[i + 1])))
                            if 300 <= val <= 900:
                                result["cibil_score"] = val
                        except (ValueError, TypeError):
                            pass
                    if 'overdue' in cell_str and i + 1 < len(row):
                        try:
                            result["overdue_amount"] = int(float(str(row[i + 1]).replace(',', '')))
                        except (ValueError, TypeError):
                            pass
    except Exception as e:
        return {"error": f"Excel parse error: {e}"}

    return result


# ─────────────────────────────────────────────────────────────
# F2: MASTER PDF/EXCEL ROUTER
# ─────────────────────────────────────────────────────────────

def handle_pdf_smart(media_url: str, content_type: str,
                     session: dict = None) -> dict:
    """
    Master router for all document types.
    1. Downloads file from Twilio URL
    2. For .xlsx → parse_excel_cibil()
    3. For PDF → extracts text → detect_doc_type() → routes to right parser
    Returns structured dict with doc_type + extracted fields.
    """
    session = session or {}

    try:
        file_bytes = download_pdf(media_url)
    except RuntimeError as e:
        return {"error": str(e), "doc_type": "unknown"}

    # ── Excel CIBIL ──
    if 'spreadsheet' in content_type or 'excel' in content_type or \
       media_url.lower().endswith('.xlsx'):
        return parse_excel_cibil(file_bytes)

    # ── PDF: detect then route ──
    if not PDF_SUPPORT:
        return {"error": "PDF parsing not available (pikepdf/pdfplumber missing).",
                "doc_type": "unknown"}

    # Step 1: Try unlocking
    try:
        name  = session.get("client_name", "client")
        dob   = session.get("dob", "01011990")
        phone = session.get("sender_phone", "9999")
        unlocked = unlock_pdf(file_bytes, name=name, dob=dob, phone=phone)
    except RuntimeError as e:
        return {"error": str(e), "doc_type": "unknown"}

    # Step 2: Extract raw text to detect type
    raw_text = ""
    try:
        with pdfplumber.open(io.BytesIO(unlocked)) as pdf:
            for page in pdf.pages[:4]:
                raw_text += (page.extract_text() or "") + "\n"
    except Exception as e:
        return {"error": f"Text extract error: {e}", "doc_type": "unknown"}

    doc_type = detect_doc_type(raw_text)

    # Step 3: Route to appropriate parser
    if doc_type == "cibil":
        return parse_cibil(unlocked)
    elif doc_type == "salary":
        return parse_salary_slip(unlocked)
    elif doc_type == "itr":
        return parse_itr(unlocked)
    elif doc_type == "bank":
        return parse_bank_statement(unlocked)
    else:
        # Unknown — try CIBIL first (most common document type sent)
        result = parse_cibil(unlocked)
        if result.get("cibil_score", 0) > 0:
            return result
        # Fall back to bank statement
        return parse_bank_statement(unlocked)
