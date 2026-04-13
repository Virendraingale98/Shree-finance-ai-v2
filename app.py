"""
=============================================================================
 SHREE FINANCE AI — MASTER APPLICATION ENGINE v3.3
 Author  : Virendra Ingale
 Stack   : Flask + Twilio + Groq + LangChain + Scikit-Learn + Google Sheets
 Deploy  : Render (Free Tier) | Local: ngrok + python app.py

 MODULES:
   ✅ M1 — Environment & Startup (auto model training)
   ✅ M2 — Google Sheets CRM (19-column schema)
   ✅ M3 — NLP Extractor (Groq llama-3.1-8b-instant, Hinglish)
   ✅ M4 — Vision Parser (Groq llama-4-scout — Screenshots)
   ✅ M5 — PDF Router (F2: CIBIL / Salary / ITR / Bank / Excel)
   ✅ M6 — ML Prediction Engine (8-feature Random Forest)
   ✅ M7 — Session Memory (Multi-turn Conversation)
   ✅ M8 — Twilio Webhook (Main Router)
   ✅ M9 — Health Check & Server Launch

 NEW in v3.3:
   ✅ F1 — CIBIL PDF Parser (score, loans, DPD, enquiries, flags)
   ✅ F2 — Multi-doc router (pdf_parsers.py)
   ✅ F3 — Auto-save + 19-col Sheets + reply builders (doc_saver.py)

 Run locally:
   set PYTHONIOENCODING=utf-8
   python app.py
=============================================================================
"""

# ─────────────────────────────────────────────────────────────
# M1: ENVIRONMENT & STARTUP
# ─────────────────────────────────────────────────────────────

import os
import io
import re
import json
import base64
import requests
import threading
from datetime import datetime
from flask import Flask, request, Response
from dotenv import load_dotenv
from twilio.rest import Client as TwilioClient

load_dotenv()

app = Flask(__name__)

# ── Auto-train model if missing ──
import joblib
import pandas as pd
import numpy as np

if not os.path.exists('credit_model.pkl') or not os.path.exists('model_features.pkl'):
    print("[STARTUP] Model not found — training now...")
    from sklearn.ensemble import RandomForestClassifier

    np.random.seed(42)
    N = 1000
    monthly_income   = np.random.randint(20000, 300000, N)
    existing_emi     = np.random.randint(0, 60000, N)
    cibil_score      = np.random.randint(300, 900, N)
    business_vintage = np.random.randint(1, 20, N)
    loan_amount      = np.random.randint(100000, 10000000, N)
    num_active_loans = np.random.randint(0, 6, N)
    industry_risk    = np.random.choice([1, 2, 3], N, p=[0.4, 0.4, 0.2])
    foir             = (existing_emi / monthly_income).round(4)

    df_train = pd.DataFrame({
        'Monthly_Income': monthly_income, 'Existing_EMI': existing_emi,
        'CIBIL_Score': cibil_score, 'Business_Vintage_Yrs': business_vintage,
        'Loan_Amount': loan_amount, 'FOIR': foir,
        'Num_Active_Loans': num_active_loans, 'Industry_Risk': industry_risk,
    })

    def approval_logic(row):
        if row['CIBIL_Score'] < 650:         return 0
        if row['FOIR'] > 0.65:               return 0
        if row['Num_Active_Loans'] >= 5:     return 0
        score = 0
        if row['CIBIL_Score'] >= 750: score += 3
        elif row['CIBIL_Score'] >= 700: score += 2
        elif row['CIBIL_Score'] >= 650: score += 1
        if row['FOIR'] < 0.30: score += 3
        elif row['FOIR'] < 0.45: score += 2
        elif row['FOIR'] < 0.55: score += 1
        if row['Business_Vintage_Yrs'] >= 5: score += 2
        elif row['Business_Vintage_Yrs'] >= 3: score += 1
        if row['Industry_Risk'] == 1: score += 1
        elif row['Industry_Risk'] == 3: score -= 1
        return 1 if score >= 5 else 0

    df_train['Loan_Approved'] = df_train.apply(approval_logic, axis=1)
    FEATURES = ['Monthly_Income', 'Existing_EMI', 'CIBIL_Score',
                'Business_Vintage_Yrs', 'Loan_Amount', 'FOIR',
                'Num_Active_Loans', 'Industry_Risk']
    model = RandomForestClassifier(n_estimators=200, max_depth=20,
                                   class_weight='balanced', random_state=42)
    model.fit(df_train[FEATURES], df_train['Loan_Approved'])
    joblib.dump(model, 'credit_model.pkl')
    joblib.dump(FEATURES, 'model_features.pkl')
    print("[STARTUP] Model trained and saved.")

saved_model    = joblib.load('credit_model.pkl')
model_features = joblib.load('model_features.pkl')
print("[STARTUP] ML model loaded successfully.")


# ─────────────────────────────────────────────────────────────
# M2: GOOGLE SHEETS CRM (19-column via doc_saver.py)
# ─────────────────────────────────────────────────────────────

from doc_saver import (
    log_19col_to_sheets,
    ensure_19_col_headers,
    save_cibil_to_session,
    save_salary_to_session,
    save_itr_to_session,
    save_bank_to_session,
    build_cibil_reply,
    build_salary_reply,
    build_itr_reply,
    build_bank_reply,
    build_next_step_prompt,
    build_unknown_doc_reply,
    _empty_session,
)

# Ensure 19-column headers at startup (non-blocking)
try:
    ensure_19_col_headers()
except Exception as _e:
    print(f"[STARTUP] Sheets header check skipped: {_e}")


# ─────────────────────────────────────────────────────────────
# M3: NLP EXTRACTOR — Groq + LangChain + Pydantic
# ─────────────────────────────────────────────────────────────

from langchain_groq import ChatGroq
from pydantic import BaseModel, Field

class LeadDataExtractor(BaseModel):
    Monthly_Income       : int       = Field(default=0,   description="Monthly income in INR.")
    Existing_EMI         : int       = Field(default=0,   description="Existing EMI per month.")
    CIBIL_Score          : int       = Field(default=0,   description="CIBIL credit score (300-900).")
    Business_Vintage_Yrs : int       = Field(default=0,   description="Years in business.")
    Loan_Amount          : int       = Field(default=0,   description="Requested loan amount in INR.")
    Num_Active_Loans     : int       = Field(default=0,   description="Number of active running loans.")
    Industry_Risk        : int       = Field(default=2,   description="Industry risk: 1=Low, 2=Med, 3=High.")
    missing_fields       : list[str] = Field(default_factory=list,
                                             description="Fields NOT mentioned.")

text_llm   = ChatGroq(model="llama-3.1-8b-instant", temperature=0,
                       api_key=os.environ.get("GROQ_API_KEY"))
translator = text_llm.with_structured_output(LeadDataExtractor)

SYSTEM_PROMPT = (
    "You are a financial data extractor for Indian loan applications. "
    "Text may be in Hinglish (Hindi-English mix) or pure English. "
    "Examples: '80k income', 'CIBIL 720', 'EMI 15 hazaar', '4 saal purana business'. "
    "Extract ONLY numerical values. Convert 'k' to thousands, 'lakh' to 100000."
)

def extract_lead_data(text: str) -> LeadDataExtractor:
    return translator.invoke(f"{SYSTEM_PROMPT}\n\nUser Input: {text}")


# ─────────────────────────────────────────────────────────────
# M4: VISION PARSER — Groq llama-4-scout (Screenshots)
# ─────────────────────────────────────────────────────────────

from groq import Groq as GroqClient

groq_client = GroqClient(api_key=os.environ.get("GROQ_API_KEY"))

def parse_screenshot_images(media_urls: list) -> dict:
    """Parse WhatsApp bank statement screenshots via Groq Vision."""
    twilio_sid   = os.environ.get("TWILIO_ACCOUNT_SID")
    twilio_token = os.environ.get("TWILIO_AUTH_TOKEN")

    image_contents = []
    for url in media_urls:
        try:
            resp    = requests.get(url, auth=(twilio_sid, twilio_token), timeout=10)
            img_b64 = base64.b64encode(resp.content).decode("utf-8")
            image_contents.append({
                "type": "image_url",
                "image_url": {"url": f"data:image/jpeg;base64,{img_b64}"}
            })
        except Exception as e:
            print(f"[VISION] Image fetch error: {e}")

    if not image_contents:
        return {"error": "Could not download images from Twilio."}

    image_contents.append({
        "type": "text",
        "text": (
            "You are a financial document analyzer for Indian bank statements. "
            "Analyze these bank statement screenshots (may be Hindi/English/Hinglish). "
            "Return ONLY valid JSON with these keys:\n"
            '{"employer_name": "string", "average_monthly_salary": 0, '
            '"salary_credits": [], "account_holder": "string", "bank_name": "string"}\n'
            "If any field is unclear, use null."
        )
    })

    response = groq_client.chat.completions.create(
        model="meta-llama/llama-4-scout-17b-16e-instruct",
        messages=[{"role": "user", "content": image_contents}],
        temperature=0,
        response_format={"type": "json_object"}
    )
    return json.loads(response.choices[0].message.content)


# ─────────────────────────────────────────────────────────────
# M5: PDF ROUTER — F2 Multi-Doc (pdf_parsers.py)
# ─────────────────────────────────────────────────────────────

from pdf_parsers import handle_pdf_smart


# ─────────────────────────────────────────────────────────────
# M6: ML PREDICTION ENGINE
# ─────────────────────────────────────────────────────────────

def run_prediction(data: dict) -> tuple:
    """Run 8-feature Random Forest. Returns (prediction, probability, foir)."""
    foir = round(data.get('Existing_EMI', 0) / data['Monthly_Income'], 4) \
           if data.get('Monthly_Income', 0) > 0 else 0

    lead_df = pd.DataFrame([[
        data.get('Monthly_Income', 0),
        data.get('Existing_EMI', 0),
        data.get('CIBIL_Score', 0),
        data.get('Business_Vintage_Yrs', 0),
        data.get('Loan_Amount', 0),
        foir,
        data.get('Num_Active_Loans', 0),
        data.get('Industry_Risk', 2),
    ]], columns=model_features)

    prediction  = saved_model.predict(lead_df)[0]
    probability = saved_model.predict_proba(lead_df)[0][1]
    return int(prediction), float(probability), foir


# ─────────────────────────────────────────────────────────────
# M7: SESSION MEMORY — Multi-turn Conversation
# ─────────────────────────────────────────────────────────────

user_sessions = {}  # {phone: session_dict}

CRITICAL_FIELDS = ['Monthly_Income', 'CIBIL_Score', 'Business_Vintage_Yrs']

def update_session(phone: str, extracted: LeadDataExtractor) -> dict:
    """Merge NLP-extracted data into session."""
    if phone not in user_sessions:
        user_sessions[phone] = _empty_session()
    sess = user_sessions[phone]
    if extracted.Monthly_Income       > 0: sess['Monthly_Income']       = extracted.Monthly_Income
    if extracted.Existing_EMI         > 0: sess['Existing_EMI']         = extracted.Existing_EMI
    if extracted.CIBIL_Score          > 0: sess['CIBIL_Score']          = extracted.CIBIL_Score
    if extracted.Business_Vintage_Yrs > 0: sess['Business_Vintage_Yrs'] = extracted.Business_Vintage_Yrs
    if extracted.Loan_Amount          > 0: sess['Loan_Amount']          = extracted.Loan_Amount
    if extracted.Num_Active_Loans     > 0: sess['Num_Active_Loans']     = extracted.Num_Active_Loans
    if extracted.Industry_Risk        > 0: sess['Industry_Risk']        = extracted.Industry_Risk
    return sess

def get_missing_fields(session: dict) -> list:
    return [f for f in CRITICAL_FIELDS if session.get(f, 0) == 0]

def clear_session(phone: str):
    user_sessions.pop(phone, None)


# ─────────────────────────────────────────────────────────────
# M8: TWILIO WEBHOOK — Main Router
# ─────────────────────────────────────────────────────────────

from twilio.twiml.messaging_response import MessagingResponse

@app.route('/whatsapp', methods=['POST'])
def whatsapp_reply():
    incoming_msg = request.values.get('Body', '').strip()
    sender_phone = request.values.get('From', '').replace('whatsapp:', '')
    num_media    = int(request.values.get('NumMedia', 0))
    reply_text   = ""

    try:
        # ══════════════════════════════════════════════
        # PATH A: Media Received (Images, PDF, Excel)
        # ══════════════════════════════════════════════
        if num_media > 0:
            media_type = request.values.get('MediaContentType0', '')
            media_url  = request.values.get('MediaUrl0', '')

            # ── A1: Image Screenshots → Vision Parser ──
            if 'image' in media_type:
                media_urls = [
                    request.values.get(f'MediaUrl{i}', '')
                    for i in range(num_media)
                ]
                result = parse_screenshot_images(media_urls)

                if 'error' in result:
                    reply_text = f"⚠️ Could not read image.\n{result['error']}"
                else:
                    salary   = result.get('average_monthly_salary', 0)
                    employer = result.get('employer_name', 'Unknown')
                    bank     = result.get('bank_name', 'Unknown Bank')

                    if phone_not_in_sessions(sender_phone):
                        user_sessions[sender_phone] = _empty_session()
                    if salary > 0:
                        user_sessions[sender_phone]['Monthly_Income']  = salary
                        user_sessions[sender_phone]['_employer_name']  = employer
                        user_sessions[sender_phone]['_doc_type']       = "Screenshot"

                    reply_text = (
                        f"📸 Screenshots Analyzed\n"
                        f"━━━━━━━━━━━━━━━━━━━━\n"
                        f"🏦 Bank     : {bank}\n"
                        f"🏢 Employer : {employer}\n"
                        f"💰 Salary   : Rs.{salary:,}\n"
                        f"💾 Income saved.\n"
                        f"━━━━━━━━━━━━━━━━━━━━\n"
                        + build_next_step_prompt(
                            user_sessions.get(sender_phone, _empty_session())
                        )
                    )

            # ── A2: PDF / Excel → Smart Router (F1+F2) ──
            elif 'application/pdf' in media_type or \
                 'spreadsheet' in media_type or \
                 'excel' in media_type:

                # ASYNC PATTERN: Reply immediately to beat Twilio's 15s timeout,
                # then process the PDF in a background thread and send the real reply.
                reply_text = (
                    "📄 Document received! Analysing your PDF...\n"
                    "Please wait ~30 seconds for the result."
                )

                # Capture variables for background thread
                _url   = media_url
                _mtype = media_type
                _phone = sender_phone

                def process_pdf_async(url, mtype, phone):
                    """Runs in background: parse PDF then send WhatsApp reply via Twilio REST API."""
                    try:
                        session_ctx = user_sessions.get(phone, {})
                        session_ctx["sender_phone"] = phone
                        result = handle_pdf_smart(url, mtype, session_ctx)

                        if 'error' in result:
                            final_reply = (
                                f"⚠️ Could not read document.\n"
                                f"Reason: {result['error']}\n\n"
                                + build_unknown_doc_reply()
                            )
                        else:
                            doc_type = result.get("doc_type", "unknown")
                            if doc_type == "cibil":
                                save_cibil_to_session(phone, result, user_sessions)
                                final_reply = build_cibil_reply(result)
                            elif doc_type == "salary":
                                save_salary_to_session(phone, result, user_sessions)
                                final_reply = build_salary_reply(result)
                            elif doc_type == "itr":
                                save_itr_to_session(phone, result, user_sessions)
                                final_reply = build_itr_reply(result)
                            elif doc_type == "bank":
                                save_bank_to_session(phone, result, user_sessions)
                                final_reply = build_bank_reply(result)
                            else:
                                final_reply = build_unknown_doc_reply()

                            # Auto-predict if all fields complete
                            sess = user_sessions.get(phone, _empty_session())
                            missing = get_missing_fields(sess)
                            if not missing and sess.get("Monthly_Income", 0) > 0:
                                pred, prob, foir = run_prediction(sess)
                                final_reply += _prediction_block(sess, pred, prob, foir, phone)

                        # Send reply via Twilio REST (not TwiML — this is outbound)
                        twilio_client = TwilioClient(
                            os.environ.get("TWILIO_ACCOUNT_SID"),
                            os.environ.get("TWILIO_AUTH_TOKEN")
                        )
                        twilio_client.messages.create(
                            from_="whatsapp:+14155238886",
                            to=f"whatsapp:{phone}",
                            body=final_reply
                        )
                        print(f"[PDF ASYNC] Reply sent to {phone}")

                    except Exception as thread_err:
                        print(f"[PDF ASYNC ERROR] {thread_err}")

                t = threading.Thread(
                    target=process_pdf_async,
                    args=(_url, _mtype, _phone),
                    daemon=True
                )
                t.start()

            else:
                reply_text = "⚠️ Please send only PDF, Excel, or image files."

        # ══════════════════════════════════════════════
        # PATH B: Text Message — NLP Extraction
        # ══════════════════════════════════════════════
        else:
            if not incoming_msg:
                reply_text = (
                    "👋 Welcome to *Shree Finance AI* v3.3!\n\n"
                    "Send your loan details as text:\n"
                    "_Example: Income 60k, CIBIL 720, EMI 10k, 4 years business_\n\n"
                    "Or upload: CIBIL PDF / Salary Slip / ITR / Bank Statement"
                )
            else:
                extracted = extract_lead_data(incoming_msg)
                session   = update_session(sender_phone, extracted)
                missing   = get_missing_fields(session)

                if missing:
                    filled = [f for f in CRITICAL_FIELDS if session.get(f, 0) > 0]
                    fill_str = ", ".join(f.replace('_', ' ') for f in filled)
                    reply_text = (
                        f"✅ Got partial data!\n"
                        f"Have : {fill_str or 'Nothing yet'}\n\n"
                        + build_next_step_prompt(session)
                    )
                else:
                    pred, prob, foir = run_prediction(session)
                    reply_text = _prediction_block(session, pred, prob, foir,
                                                   sender_phone)

    except Exception as e:
        reply_text = f"⚠️ System Error: {str(e)}"
        print(f"[ERROR] {e}")

    resp = MessagingResponse()
    resp.message().body(reply_text)
    return Response(str(resp), mimetype='application/xml')


# ─────────────────────────────────────────────────────────────
# HELPER: Prediction result block
# ─────────────────────────────────────────────────────────────

def phone_not_in_sessions(phone: str) -> bool:
    return phone not in user_sessions

def _prediction_block(session: dict, pred: int, prob: float,
                       foir: float, phone: str) -> str:
    """Build the final loan decision reply and log to Sheets if approved."""
    status      = "✅ APPROVED" if pred == 1 else "❌ REJECTED"
    foir_status = "OK ✅" if foir < 0.5 else "HIGH ⚠️"

    block = (
        f"\n\n🏦 *Shree Finance AI v3.3*\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"💰 Income    : Rs.{session.get('Monthly_Income', 0):,}\n"
        f"📊 CIBIL     : {session.get('CIBIL_Score', 0)}\n"
        f"💳 EMI       : Rs.{session.get('Existing_EMI', 0):,}\n"
        f"📈 FOIR      : {foir * 100:.1f}% ({foir_status})\n"
        f"📅 Vintage   : {session.get('Business_Vintage_Yrs', 0)} yrs\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"🎯 Decision  : *{status}*\n"
        f"🔢 Confidence: {prob * 100:.1f}%\n"
    )

    if pred == 1:
        log_19col_to_sheets(phone, session, prob)
        block += (
            f"💾 Lead saved to CRM (19 columns).\n"
            f"📲 Our team will call you within 24 hours!"
        )
    else:
        reasons = []
        if session.get('CIBIL_Score', 0) < 700:    reasons.append("Low CIBIL score")
        if foir > 0.5:                              reasons.append("High FOIR")
        if session.get('Business_Vintage_Yrs', 0) < 2: reasons.append("New business")
        if session.get("_cibil_neg_flags", []):    reasons.append("Negative credit flags")
        block += (
            f"📋 Reasons: {' | '.join(reasons) if reasons else 'Multiple factors'}\n"
            f"💡 Advise client to improve credit profile."
        )

    clear_session(phone)
    return block


# ─────────────────────────────────────────────────────────────
# M9: HEALTH CHECK & SERVER LAUNCH
# ─────────────────────────────────────────────────────────────

@app.route('/', methods=['GET'])
def health_check():
    """Health check — keeps Render free tier alive via UptimeRobot."""
    return {
        "status"  : "✅ Shree Finance AI is running",
        "version" : "3.3",
        "features": ["F1:CIBIL", "F2:MultiPDF", "F3:AutoSave-19col"],
        "model"   : "RandomForest 8-feature",
        "author"  : "Virendra Ingale",
        "time"    : datetime.now().strftime("%Y-%m-%d %H:%M:%S IST")
    }, 200

@app.route('/ping', methods=['GET'])
def ping():
    return "pong", 200

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)
