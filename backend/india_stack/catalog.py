"""India Stack component catalog.

Each component declares:
    id           – stable slug used in DB + URLs
    name         – display name
    category     – Identity | Payments | DataSharing
    description  – 1-line summary shown in the palette
    scope        – 'service' (becomes its own microservice) | 'capability' (attaches to existing service)
    sandbox_providers – list of vendor names the user can pick when switching from mock to real sandbox
    env_vars     – list of (env_var, hint) tuples to render in Config card
    endpoints    – list of API endpoints the CodeGen step will scaffold
    frontend     – frontend React component(s) to scaffold
    consent_kind – what kind of consent/audit record the integration produces (None when not applicable)
"""
from __future__ import annotations
from typing import Dict, List, Any

CATALOG: List[Dict[str, Any]] = [
    {
        "id": "aadhaar_ekyc",
        "name": "Aadhaar eKYC (OTP)",
        "category": "Identity",
        "description": "UIDAI Aadhaar OTP-based eKYC. User enters Aadhaar number, receives OTP, you get demographics + photo.",
        "scope": "capability",
        "sandbox_providers": ["Setu", "Karza", "Signzy", "Sandbox.co.in"],
        "env_vars": [
            ("AADHAAR_PROVIDER", "mock | setu | karza | signzy | sandbox"),
            ("AADHAAR_BASE_URL", "Provider sandbox URL"),
            ("AADHAAR_CLIENT_ID", "Provider client ID"),
            ("AADHAAR_CLIENT_SECRET", "Provider client secret"),
        ],
        "endpoints": [
            ("POST", "/india/ekyc/initiate", "Accept aadhaar_number, send OTP, return transaction_id"),
            ("POST", "/india/ekyc/verify", "Accept transaction_id + otp, return user demographics"),
        ],
        "frontend": [
            "AadhaarOtpModal.jsx — modal with Aadhaar input + OTP step",
            "useAadhaarEkyc.js — hook wrapping initiate/verify calls",
        ],
        "consent_kind": "ekyc",
    },
    {
        "id": "aadhaar_esign",
        "name": "Aadhaar e-Sign",
        "category": "Identity",
        "description": "OTP-based digital signature on PDF documents using Aadhaar. Compliant with IT Act 2000.",
        "scope": "capability",
        "sandbox_providers": ["Setu", "NSDL", "Signzy"],
        "env_vars": [
            ("ESIGN_PROVIDER", "mock | setu | nsdl | signzy"),
            ("ESIGN_BASE_URL", "Provider sandbox URL"),
            ("ESIGN_API_KEY", "Provider API key"),
            ("ESIGN_CALLBACK_URL", "Your public callback URL"),
        ],
        "endpoints": [
            ("POST", "/india/esign/request", "Upload document, return signing URL"),
            ("POST", "/india/esign/callback", "Provider callback storing signed PDF"),
            ("GET", "/india/esign/{request_id}", "Fetch signed PDF / status"),
        ],
        "frontend": ["EsignButton.jsx — opens provider URL in popup + polls completion"],
        "consent_kind": "esign",
    },
    {
        "id": "digilocker",
        "name": "DigiLocker",
        "category": "Identity",
        "description": "Fetch driving licence, PAN, marksheets, etc. from MeitY's DigiLocker with citizen consent.",
        "scope": "capability",
        "sandbox_providers": ["Setu", "Karza", "Sandbox.co.in"],
        "env_vars": [
            ("DIGILOCKER_PROVIDER", "mock | setu | karza | sandbox"),
            ("DIGILOCKER_CLIENT_ID", "Provider client ID"),
            ("DIGILOCKER_CLIENT_SECRET", "Provider client secret"),
            ("DIGILOCKER_REDIRECT_URI", "OAuth redirect URI"),
        ],
        "endpoints": [
            ("GET",  "/india/digilocker/authorize", "Redirect user to DigiLocker consent"),
            ("GET",  "/india/digilocker/callback", "OAuth callback storing access token"),
            ("GET",  "/india/digilocker/documents", "List available documents"),
            ("GET",  "/india/digilocker/document/{doc_id}", "Download a document"),
        ],
        "frontend": ["DigilockerConnect.jsx — connect button + document picker"],
        "consent_kind": "digilocker",
    },
    {
        "id": "meripehchaan",
        "name": "MeriPehchaan SSO",
        "category": "Identity",
        "description": "Government Single Sign-On (NSSO). One identity across central + state portals.",
        "scope": "capability",
        "sandbox_providers": ["NSSO sandbox"],
        "env_vars": [
            ("MERIPEHCHAAN_CLIENT_ID", "NSSO client ID"),
            ("MERIPEHCHAAN_CLIENT_SECRET", "NSSO client secret"),
            ("MERIPEHCHAAN_REDIRECT_URI", "Your callback URL"),
        ],
        "endpoints": [
            ("GET", "/india/sso/login", "Kick off MeriPehchaan OAuth"),
            ("GET", "/india/sso/callback", "OAuth callback creating local user session"),
        ],
        "frontend": ["MeriPehchaanLoginButton.jsx"],
        "consent_kind": None,
    },
    {
        "id": "upi",
        "name": "UPI (Collect / Intent / Mandate)",
        "category": "Payments",
        "description": "NPCI UPI rails: collect requests, intent links, recurring mandates (UPI AutoPay).",
        "scope": "service",
        "sandbox_providers": ["Cashfree", "Razorpay", "PhonePe Business", "Decentro"],
        "env_vars": [
            ("UPI_PROVIDER", "mock | cashfree | razorpay | phonepe | decentro"),
            ("UPI_MERCHANT_ID", "Provider merchant ID"),
            ("UPI_KEY_ID", "API key"),
            ("UPI_KEY_SECRET", "API secret"),
            ("UPI_WEBHOOK_SECRET", "Webhook signing key"),
        ],
        "endpoints": [
            ("POST", "/india/upi/collect", "Create collect request (push to VPA)"),
            ("POST", "/india/upi/intent",  "Generate intent link / QR"),
            ("POST", "/india/upi/mandate", "Create recurring mandate"),
            ("POST", "/india/upi/webhook", "Provider webhook for status updates"),
            ("GET",  "/india/upi/txn/{txn_id}", "Get transaction status"),
        ],
        "frontend": [
            "UpiPaymentSheet.jsx — sheet with VPA input + intent QR fallback",
            "useUpiPayment.js — hook polling txn status",
        ],
        "consent_kind": None,
    },
    {
        "id": "bbps",
        "name": "BBPS (Bharat Bill Payment)",
        "category": "Payments",
        "description": "Pay any biller registered with BBPS (electricity, gas, broadband, FASTag, etc.).",
        "scope": "service",
        "sandbox_providers": ["Cashfree", "Setu", "Decentro"],
        "env_vars": [
            ("BBPS_PROVIDER", "mock | cashfree | setu | decentro"),
            ("BBPS_AGENT_ID", "BBPOU agent ID"),
            ("BBPS_API_KEY", "API key"),
        ],
        "endpoints": [
            ("GET",  "/india/bbps/billers",     "Search billers by category / pincode"),
            ("POST", "/india/bbps/fetch-bill",  "Fetch bill amount for a customer"),
            ("POST", "/india/bbps/pay",         "Pay the fetched bill"),
            ("GET",  "/india/bbps/receipt/{txn_id}", "Download receipt"),
        ],
        "frontend": ["BbpsPayBill.jsx — biller search + bill fetch + pay"],
        "consent_kind": None,
    },
    {
        "id": "account_aggregator",
        "name": "Account Aggregator (RBI AA)",
        "category": "DataSharing",
        "description": "RBI's consent-based financial data sharing framework (DEPA). Pull bank statements, mutual funds, NPS, etc.",
        "scope": "service",
        "sandbox_providers": ["Setu", "Finvu", "OneMoney", "NADL"],
        "env_vars": [
            ("AA_PROVIDER", "mock | setu | finvu | onemoney | nadl"),
            ("AA_BASE_URL", "Provider sandbox URL"),
            ("AA_CLIENT_ID", "AA Client ID"),
            ("AA_CLIENT_SECRET", "AA Client Secret"),
            ("AA_FIU_ID", "Your FIU registration ID with ReBIT"),
        ],
        "endpoints": [
            ("POST", "/india/aa/consent",     "Create consent request, return consent handle"),
            ("GET",  "/india/aa/consent/{handle}", "Poll consent status"),
            ("POST", "/india/aa/data-request", "Trigger FIP data pull after consent approval"),
            ("GET",  "/india/aa/data/{session_id}", "Fetch decrypted data"),
            ("POST", "/india/aa/notify",      "AA notification webhook"),
        ],
        "frontend": [
            "AaConsentFlow.jsx — initiate consent + open AA App / poll status",
            "AaDataView.jsx — render pulled financial accounts",
        ],
        "consent_kind": "aa_consent",
    },
]


def by_id(component_id: str) -> Dict[str, Any] | None:
    for c in CATALOG:
        if c["id"] == component_id:
            return c
    return None
