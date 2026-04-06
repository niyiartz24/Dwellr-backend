"""
Dwellr - Payment Routes
Handles Paystack payment verification before a listing is saved.
"""

import os
import requests
from flask import Blueprint, jsonify

payment_bp = Blueprint("payment", __name__, url_prefix="/payment")

PAYSTACK_VERIFY_URL = "https://api.paystack.co/transaction/verify/"


def verify_paystack_reference(reference: str) -> dict:
    """
    Call Paystack's verify endpoint and return the transaction data.
    Raises ValueError if verification fails or payment was not successful.
    """
    secret = os.getenv("PAYSTACK_SECRET_KEY", "")
    if not secret:
        raise ValueError("PAYSTACK_SECRET_KEY is not configured on the server.")

    resp = requests.get(
        PAYSTACK_VERIFY_URL + reference,
        headers={"Authorization": f"Bearer {secret}"},
        timeout=10,
    )

    if resp.status_code != 200:
        raise ValueError(f"Paystack API returned status {resp.status_code}.")

    data = resp.json()

    if not data.get("status"):
        raise ValueError(data.get("message", "Paystack verification failed."))

    tx = data.get("data", {})
    if tx.get("status") != "success":
        raise ValueError(f"Payment status is '{tx.get('status')}', not 'success'.")

    return tx   # contains amount (in kobo), reference, customer, etc.


@payment_bp.route("/verify/<reference>", methods=["GET"])
def verify(reference):
    """
    GET /payment/verify/<reference>

    Verifies a Paystack transaction reference.
    Returns the transaction amount (in Naira) and status.
    """
    try:
        tx = verify_paystack_reference(reference)
        return jsonify({
            "success":   True,
            "reference": tx.get("reference"),
            "amount":    tx.get("amount", 0) / 100,   # kobo → Naira
            "status":    tx.get("status"),
            "email":     tx.get("customer", {}).get("email", ""),
        }), 200
    except ValueError as e:
        return jsonify({"success": False, "error": str(e)}), 402
    except Exception as e:
        return jsonify({"success": False, "error": f"Verification error: {str(e)}"}), 500
