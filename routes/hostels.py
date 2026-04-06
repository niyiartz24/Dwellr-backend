"""
Dwellr - Hostel Routes Blueprint
RESTful API endpoints for hostel resource management.
"""

from flask import Blueprint, request, jsonify
from routes.payment import verify_paystack_reference
from models import (
    get_all_hostels,
    get_hostel_by_id,
    create_hostel,
    update_hostel,
    delete_hostel,
)

hostels_bp = Blueprint("hostels", __name__, url_prefix="/hostels")

# ---------------------------------------------------------------------------
# Validation helpers
# ---------------------------------------------------------------------------

REQUIRED_FIELDS = ["name", "location", "price"]
VALID_HOSTEL_TYPES = ("male", "female", "mixed")


def validate_hostel_data(data, require_all=True):
    """
    Validate hostel payload.
    Returns (is_valid, error_message).
    """
    if require_all:
        for field in REQUIRED_FIELDS:
            if data.get(field) in (None, "", 0):
                return False, f"'{field}' is required and cannot be empty."

    if "price" in data and data["price"] is not None:
        try:
            price = int(data["price"])
            if price <= 0:
                return False, "Price must be a positive number."
        except (ValueError, TypeError):
            return False, "Price must be a valid integer."

    if "available_rooms" in data and data["available_rooms"] is not None:
        try:
            rooms = int(data["available_rooms"])
            if rooms < 0:
                return False, "Available rooms cannot be negative."
        except (ValueError, TypeError):
            return False, "Available rooms must be a valid integer."

    if "hostel_type" in data and data["hostel_type"] not in VALID_HOSTEL_TYPES:
        return False, f"hostel_type must be one of: {', '.join(VALID_HOSTEL_TYPES)}."

    if "name" in data and data["name"] and len(str(data["name"]).strip()) < 3:
        return False, "Hostel name must be at least 3 characters."

    if "location" in data and data["location"] and len(str(data["location"]).strip()) < 3:
        return False, "Location must be at least 3 characters."

    if "contact" in data and data["contact"]:
        contact = str(data["contact"]).strip()
        if len(contact) < 7:
            return False, "Contact number appears too short."

    return True, None


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@hostels_bp.route("", methods=["GET"])
def list_hostels():
    """
    GET /hostels
    GET /hostels?location=Yaba&price=50000&type=mixed
    """
    location   = request.args.get("location", "").strip() or None
    max_price  = request.args.get("price",    "").strip() or None
    hostel_type = request.args.get("type",   "").strip() or None

    try:
        hostels = get_all_hostels(location=location, max_price=max_price, hostel_type=hostel_type)
        return jsonify({"success": True, "count": len(hostels), "data": hostels}), 200
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@hostels_bp.route("/<int:hostel_id>", methods=["GET"])
def get_hostel(hostel_id):
    """GET /hostels/<id>"""
    try:
        hostel = get_hostel_by_id(hostel_id)
        if not hostel:
            return jsonify({"success": False, "error": "Hostel not found."}), 404
        return jsonify({"success": True, "data": hostel}), 200
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@hostels_bp.route("", methods=["POST"])
def add_hostel():
    """
    POST /hostels
    Accepts JSON body (Content-Type: application/json).
    Uses force=True so it parses JSON even if the Content-Type header is
    missing or wrong — the most common source of silent failures.
    """
    data = request.get_json(force=True, silent=True)

    if not data:
        raw = request.get_data(as_text=True)
        return jsonify({
            "success": False,
            "error": "Request body must be valid JSON.",
            "hint": "Ensure Content-Type is application/json and body is well-formed.",
            "received": raw[:300] if raw else "(empty body)"
        }), 400

    # Sanitise strings
    for key in ("name", "location", "description", "image_url", "contact", "hostel_type"):
        if key in data and isinstance(data[key], str):
            data[key] = data[key].strip()

    is_valid, error = validate_hostel_data(data, require_all=True)
    if not is_valid:
        return jsonify({"success": False, "error": error}), 422

    # ------------------------------------------------------------------
    # Payment verification — 1% of listing price must be paid via Paystack.
    # The frontend sends the Paystack transaction reference in the payload.
    # We verify it server-side before saving anything to the database.
    # ------------------------------------------------------------------
    reference = data.pop("payment_reference", "").strip()
    if not reference:
        return jsonify({
            "success": False,
            "error": "A valid payment reference is required to list a property."
        }), 402

    try:
        tx = verify_paystack_reference(reference)

        # Cross-check: amount paid must be >= 1% of listing price (in kobo)
        listing_price = int(data.get("price", 0))
        expected_kobo = int(listing_price * 0.01 * 100)   # 1% in kobo
        paid_kobo     = int(tx.get("amount", 0))

        # Allow a tiny tolerance (1 kobo) for rounding
        if paid_kobo < expected_kobo - 1:
            return jsonify({
                "success": False,
                "error": (
                    f"Payment amount mismatch. "
                    f"Expected at least \u20a6{expected_kobo / 100:,.0f}, "
                    f"received \u20a6{paid_kobo / 100:,.0f}."
                )
            }), 402

    except ValueError as e:
        return jsonify({"success": False, "error": str(e)}), 402
    except Exception as e:
        return jsonify({"success": False, "error": f"Payment verification failed: {str(e)}"}), 500

    try:
        hostel = create_hostel(data)
        return jsonify({
            "success":     True,
            "data":        hostel,
            "admin_token": hostel.get("admin_token", ""),
        }), 201
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@hostels_bp.route("/<int:hostel_id>", methods=["PUT", "PATCH"])
def edit_hostel(hostel_id):
    """PUT/PATCH /hostels/<id>"""
    data = request.get_json(force=True, silent=True)
    if not data:
        return jsonify({"success": False, "error": "Request body must be valid JSON."}), 400

    existing = get_hostel_by_id(hostel_id)
    if not existing:
        return jsonify({"success": False, "error": "Hostel not found."}), 404

    for key in ("name", "location", "description", "image_url", "contact", "hostel_type"):
        if key in data and isinstance(data[key], str):
            data[key] = data[key].strip()

    is_valid, error = validate_hostel_data(data, require_all=False)
    if not is_valid:
        return jsonify({"success": False, "error": error}), 422

    try:
        updated = update_hostel(hostel_id, data)
        return jsonify({"success": True, "data": updated}), 200
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@hostels_bp.route("/<int:hostel_id>", methods=["DELETE"])
def remove_hostel(hostel_id):
    """DELETE /hostels/<id>"""
    try:
        deleted = delete_hostel(hostel_id)
        if not deleted:
            return jsonify({"success": False, "error": "Hostel not found."}), 404
        return jsonify({"success": True, "message": "Hostel deleted successfully."}), 200
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500
