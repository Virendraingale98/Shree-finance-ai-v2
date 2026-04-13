"""
=============================================================================
 SHREE FINANCE AI v3.3 — OFFLINE UNIT TESTS
 Author  : Virendra Ingale
 File    : test_parsers.py
 Usage   : python test_parsers.py
 Notes   : No API key or internet needed — 100% offline tests
=============================================================================
"""

import sys
import unittest


class TestDocTypeDetector(unittest.TestCase):
    """Test detect_doc_type() keyword scoring."""

    def setUp(self):
        from pdf_parsers import detect_doc_type
        self.detect = detect_doc_type

    def test_detect_cibil(self):
        text = (
            "CIBIL Score Report\n"
            "Credit Score: 730\n"
            "Days Past Due: 0\n"
            "Credit Enquiries: 2\n"
            "Overdue Amount: 0\n"
        )
        result = self.detect(text)
        self.assertEqual(result, "cibil", f"Expected 'cibil', got '{result}'")

    def test_detect_salary(self):
        text = (
            "Salary Slip — March 2025\n"
            "Employee Name: Virendra Ingale\n"
            "Gross Salary: 65000\n"
            "PF Deduction: 2000\n"
            "Net Pay: 58000\n"
        )
        result = self.detect(text)
        self.assertEqual(result, "salary", f"Expected 'salary', got '{result}'")

    def test_detect_itr(self):
        text = (
            "Income Tax Return — AY 2024-25\n"
            "PAN Number: ABCDE1234F\n"
            "Gross Total Income: 720000\n"
            "TDS Deducted: 12000\n"
            "Form 16\n"
        )
        result = self.detect(text)
        self.assertEqual(result, "itr", f"Expected 'itr', got '{result}'")

    def test_detect_bank(self):
        text = (
            "Bank Statement — HDFC Bank\n"
            "Account Statement for Period: Jan–Jun 2025\n"
            "Opening Balance: 12500\n"
            "Closing Balance: 34800\n"
            "Transaction Date  Description  Debit  Credit\n"
        )
        result = self.detect(text)
        self.assertEqual(result, "bank", f"Expected 'bank', got '{result}'")


class TestCibilRegex(unittest.TestCase):
    """Test CIBIL score extraction from text."""

    def test_parse_cibil_score_from_text(self):
        import re
        text = "Your CIBIL Score: 745\nActive Loans: 2\nOverdue: Rs.0"
        # Simulate the score extraction in parse_cibil
        m = re.search(r'(?:cibil\s*score|credit\s*score)[^\d]*(\d{3})', text, re.IGNORECASE)
        self.assertIsNotNone(m, "CIBIL score regex should match")
        score = int(m.group(1))
        self.assertEqual(score, 745, f"Expected 745, got {score}")

    def test_parse_cibil_active_loans(self):
        import re
        text = "Active Accounts: 3\nMax DPD: 0 days\nEnquiries last 6 months: 1"
        m = re.search(r'(?:active|open)\s*(?:loan|account)[s]?[^\d]*(\d{1,2})', text, re.IGNORECASE)
        self.assertIsNotNone(m, "Active loans regex should match")
        self.assertEqual(int(m.group(1)), 3)

    def test_parse_cibil_negative_flags(self):
        import re
        text = "Account Status: SETTLED\nPayment History: Regular"
        flags = []
        negative_keywords = {
            'SETTLED': r'\bsettled\b',
            'WRITTEN OFF': r'\bwritten[\s-]?off\b',
        }
        for label, pat in negative_keywords.items():
            if re.search(pat, text, re.IGNORECASE):
                flags.append(label)
        self.assertIn('SETTLED', flags, "Should detect SETTLED flag")


class TestSalaryRegex(unittest.TestCase):
    """Test salary extraction from salary slip text."""

    def test_net_salary_extraction(self):
        import re
        text = (
            "Company: Infosys Ltd\n"
            "Employee: Virendra Ingale\n"
            "Gross Salary: 70,000\n"
            "PF Deduction: 5,000\n"
            "Net Pay: 62,500\n"
        )
        m = re.search(r'net\s*(?:pay|salary|take\s*home)[^\d]*([\d,]+)', text, re.IGNORECASE)
        self.assertIsNotNone(m, "Net salary regex should match")
        val = int(m.group(1).replace(',', ''))
        self.assertEqual(val, 62500, f"Expected 62500, got {val}")


class TestReplyBuilders(unittest.TestCase):
    """Test WhatsApp reply builder functions."""

    def test_build_cibil_reply_good_score(self):
        from doc_saver import build_cibil_reply
        data = {
            "cibil_score": 730,
            "active_loans": 2,
            "overdue_amount": 0,
            "max_dpd": 0,
            "enquiries_6m": 1,
            "negative_flags": [],
        }
        reply = build_cibil_reply(data)
        self.assertIn("730", reply)
        self.assertIn("Good", reply)
        self.assertIn("No negative flags", reply)

    def test_build_cibil_reply_poor_score_with_flags(self):
        from doc_saver import build_cibil_reply
        data = {
            "cibil_score": 580,
            "active_loans": 4,
            "overdue_amount": 25000,
            "max_dpd": 90,
            "enquiries_6m": 7,
            "negative_flags": ["SETTLED", "WRITTEN OFF"],
        }
        reply = build_cibil_reply(data)
        self.assertIn("580", reply)
        self.assertIn("Poor", reply)
        self.assertIn("SETTLED", reply)

    def test_build_next_step_all_missing(self):
        from doc_saver import build_next_step_prompt, _empty_session
        sess = _empty_session()
        prompt = build_next_step_prompt(sess)
        self.assertIn("Salary", prompt)
        self.assertIn("CIBIL", prompt)

    def test_build_next_step_nothing_missing(self):
        from doc_saver import build_next_step_prompt
        sess = {
            "Monthly_Income": 60000,
            "CIBIL_Score": 720,
            "Business_Vintage_Yrs": 4,
        }
        prompt = build_next_step_prompt(sess)
        self.assertIn("All data collected", prompt)

    def test_build_salary_reply(self):
        from doc_saver import build_salary_reply
        data = {
            "net_salary": 58000,
            "gross_salary": 65000,
            "employer_name": "Tata Motors",
            "pay_month": "March 2025",
            "employee_name": "Virendra Ingale",
        }
        reply = build_salary_reply(data)
        self.assertIn("58,000", reply)
        self.assertIn("Tata Motors", reply)


# ─────────────────────────────────────────────────────────────
# MAIN TEST RUNNER
# ─────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("=" * 60)
    print(" SHREE FINANCE AI v3.3 — OFFLINE UNIT TESTS")
    print("=" * 60)

    loader = unittest.TestLoader()
    suite  = unittest.TestSuite()

    suite.addTests(loader.loadTestsFromTestCase(TestDocTypeDetector))
    suite.addTests(loader.loadTestsFromTestCase(TestCibilRegex))
    suite.addTests(loader.loadTestsFromTestCase(TestSalaryRegex))
    suite.addTests(loader.loadTestsFromTestCase(TestReplyBuilders))

    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)

    total  = result.testsRun
    passed = total - len(result.failures) - len(result.errors)
    print(f"\n{'='*60}")
    print(f" RESULT: {passed}/{total} PASS")
    if passed == total:
        print(" [PASS] All tests passed! Ready to deploy.")
    else:
        print(" ❌ Some tests failed. Fix before deploying.")
    print(f"{'='*60}")

    sys.exit(0 if result.wasSuccessful() else 1)
