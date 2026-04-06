"""
Dwellr - Agent Panel Routes
Token-protected endpoints for agents to manage their own listings.
"""

from flask import Blueprint, request, jsonify
from models import (
    get_hostels_by_token,
    get_hostel_by_id,
    token_owns_hostel,
    update_hostel,
    delete_hostel,
)

panel_bp = Blueprint("panel", __name__, url_prefix="/panel")


def require_token(token):
    """Return 401 response if token is blank, else None."""
    if not token or len(token.strip()) < 10:
        return jsonify({"success": False, "error": "Invalid or missing admin token."}), 401
    return None


@panel_bp.route("/<token>", methods=["GET"])
def get_panel(token):
    """
    GET /panel/<token>
    Returns all listings + aggregate stats for this agent.
    """
    err = require_token(token)
    if err:
        return err

    try:
        hostels = get_hostels_by_token(token)
        if not hostels:
            return jsonify({
                "success": False,
                "error": "No listings found for this token. The link may be incorrect."
            }), 404

        total_listings  = len(hostels)
        total_rooms     = sum(h.get("available_rooms", 0) for h in hostels)
        avg_price       = int(sum(h.get("price", 0) for h in hostels) / total_listings) if total_listings else 0
        types_covered   = list({h.get("hostel_type", "mixed") for h in hostels})

        return jsonify({
            "success": True,
            "stats": {
                "total_listings":  total_listings,
                "total_rooms":     total_rooms,
                "avg_price":       avg_price,
                "types_covered":   types_covered,
            },
            "data": hostels,
        }), 200

    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@panel_bp.route("/<token>/listings/<int:hostel_id>", methods=["PATCH"])
def update_listing(token, hostel_id):
    """
    PATCH /panel/<token>/listings/<id>
    Agent can update available_rooms, description, contact, hostel_type, amenities.
    Price and name changes are not allowed after listing (would require re-verification).
    """
    err = require_token(token)
    if err:
        return err

    if not token_owns_hostel(token, hostel_id):
        return jsonify({"success": False, "error": "Access denied. This listing does not belong to your account."}), 403

    data = request.get_json(force=True, silent=True)
    if not data:
        return jsonify({"success": False, "error": "Request body must be valid JSON."}), 400

    # Strip fields agents cannot change via the panel
    for locked in ("price", "name", "admin_token", "payment_reference"):
        data.pop(locked, None)

    if "available_rooms" in data:
        try:
            rooms = int(data["available_rooms"])
            if rooms < 0:
                return jsonify({"success": False, "error": "Available rooms cannot be negative."}), 422
            data["available_rooms"] = rooms
        except (ValueError, TypeError):
            return jsonify({"success": False, "error": "Available rooms must be a number."}), 422

    try:
        updated = update_hostel(hostel_id, data)
        return jsonify({"success": True, "data": updated}), 200
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@panel_bp.route("/<token>/listings/<int:hostel_id>", methods=["DELETE"])
def delete_listing(token, hostel_id):
    """
    DELETE /panel/<token>/listings/<id>
    Permanently removes a listing. Requires token ownership.
    """
    err = require_token(token)
    if err:
        return err

    if not token_owns_hostel(token, hostel_id):
        return jsonify({"success": False, "error": "Access denied. This listing does not belong to your account."}), 403

    try:
        deleted = delete_hostel(hostel_id)
        if not deleted:
            return jsonify({"success": False, "error": "Listing not found."}), 404
        return jsonify({"success": True, "message": "Listing removed successfully."}), 200
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500
