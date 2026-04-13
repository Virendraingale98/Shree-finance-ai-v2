import pandas as pd
import numpy as np
from sklearn.ensemble import RandomForestClassifier
from sklearn.model_selection import train_test_split
import joblib

print("=" * 50)
print(" SHREE FINANCE AI v3.3 — MODEL TRAINER")
print("=" * 50)

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

df = pd.DataFrame({
    'Monthly_Income'      : monthly_income,
    'Existing_EMI'        : existing_emi,
    'CIBIL_Score'         : cibil_score,
    'Business_Vintage_Yrs': business_vintage,
    'Loan_Amount'         : loan_amount,
    'FOIR'                : foir,
    'Num_Active_Loans'    : num_active_loans,
    'Industry_Risk'       : industry_risk,
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

df['Loan_Approved'] = df.apply(approval_logic, axis=1)

FEATURES = ['Monthly_Income', 'Existing_EMI', 'CIBIL_Score',
            'Business_Vintage_Yrs', 'Loan_Amount', 'FOIR',
            'Num_Active_Loans', 'Industry_Risk']

X = df[FEATURES]
y = df['Loan_Approved']
X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42)

model = RandomForestClassifier(
    n_estimators=200, max_depth=20,
    class_weight='balanced', random_state=42
)
model.fit(X_train, y_train)

acc = model.score(X_test, y_test)
print(f"[OK] Model accuracy: {acc * 100:.1f}%")
print(f"[OK] Class distribution: {y.value_counts().to_dict()}")

joblib.dump(model, 'credit_model.pkl')
joblib.dump(FEATURES, 'model_features.pkl')
print("[OK] Saved: credit_model.pkl + model_features.pkl")
print("=" * 50)
print(" [DONE] Model training complete!")
print("=" * 50)
