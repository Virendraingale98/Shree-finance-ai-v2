"""
=============================================================================
 SHREE FINANCE AI v3.3 — DATABASE SETUP & TEST
 Author  : Virendra Ingale
 File    : test_db.py
 Usage   : python test_db.py
 Purpose : Verify Google Sheets connection + ensure 19-column headers
=============================================================================
"""

import os
import sys
import json
import gspread
from oauth2client.service_account import ServiceAccountCredentials

SHEET_NAME = "Approved Leads - Shree Finance"

HEADERS_19 = [
    "Timestamp", "Sender_Phone", "Monthly_Income", "Existing_EMI",
    "CIBIL_Score", "Business_Vintage_Yrs", "Loan_Amount", "FOIR",
    "Approval_Confidence", "Num_Active_Loans", "Overdue_Amount",
    "Max_DPD", "Enquiries_6m", "Negative_Flags", "Employer_Name",
    "ITR_Income", "Doc_Type_Received", "Docs_Received", "Reminder_Sent",
]


def connect():
    scope = ['https://spreadsheets.google.com/feeds',
             'https://www.googleapis.com/auth/drive']
    cred_path = os.path.join(os.path.dirname(__file__), 'credentials.json')

    if not os.path.exists(cred_path):
        print("[ERROR] credentials.json not found.")
        print("Please place your Google Service Account JSON as 'credentials.json'.")
        sys.exit(1)

    try:
        creds  = ServiceAccountCredentials.from_json_keyfile_name(cred_path, scope)
        client = gspread.authorize(creds)
        print("[OK] Google Sheets authenticated.")
        return client
    except Exception as e:
        print(f"[ERROR] Auth failed: {e}")
        sys.exit(1)


def setup_headers(sheet):
    """Check and write 19-column headers if needed."""
    try:
        existing = sheet.row_values(1)
        if existing == HEADERS_19:
            print("[OK] 19-column headers already in place.")
            return True

        if existing:
            print(f"[WARN] Existing headers: {len(existing)} columns — expected 19.")
            confirm = input("Overwrite with 19-column headers? (yes/no): ").strip().lower()
            if confirm != 'yes':
                print("Skipped header update.")
                return False
            sheet.delete_rows(1)

        sheet.insert_row(HEADERS_19, 1)
        print("[OK] 19-column headers written successfully.")
        return True
    except Exception as e:
        print(f"[ERROR] Header setup failed: {e}")
        return False


def test_append(sheet):
    """Write a test row and immediately delete it."""
    from datetime import datetime
    test_row = [
        datetime.now().strftime("%Y-%m-%d %H:%M:%S"),  # 1 Timestamp
        "+91-TEST-0000",                                # 2 Phone
        60000, 10000, 720, 4, 500000,                   # 3-7
        "20.0%", "78.5%",                               # 8-9 FOIR, Confidence
        2, 0, 0, 1, "None",                             # 10-14 CIBIL fields
        "Test Employer", 720000,                        # 15-16
        "TEST", "Yes", "No",                            # 17-19
    ]
    try:
        sheet.append_row(test_row)
        print("[OK] Test row appended.")
        # Remove the test row
        all_vals = sheet.get_all_values()
        last_row = len(all_vals)
        if all_vals[last_row - 1][1] == "+91-TEST-0000":
            sheet.delete_rows(last_row)
            print("[OK] Test row cleaned up.")
    except Exception as e:
        print(f"[ERROR] Test append failed: {e}")


def main():
    print("=" * 60)
    print(" SHREE FINANCE AI v3.3 — SHEETS DB TEST")
    print("=" * 60)

    client = connect()

    try:
        sheet = client.open(SHEET_NAME).sheet1
        print(f"[OK] Sheet '{SHEET_NAME}' opened.")
    except gspread.exceptions.SpreadsheetNotFound:
        print(f"[ERROR] Sheet '{SHEET_NAME}' not found.")
        print("Please create it and share with the service account email.")
        sys.exit(1)

    # Check / write 19-col headers
    setup_headers(sheet)

    # Test append + delete
    do_test = input("\nRun test row append? (yes/no): ").strip().lower()
    if do_test == 'yes':
        test_append(sheet)

    row_count = len(sheet.get_all_values()) - 1
    print(f"\n[OK] Sheet has {row_count} data row(s) (excluding header).")
    print("=" * 60)
    print(" [DONE] Database test complete!")
    print("=" * 60)


if __name__ == "__main__":
    main()
