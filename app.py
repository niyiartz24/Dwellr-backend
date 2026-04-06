"""
Dwellr - Flask Application Entry Point
Student accommodation finder platform backend.
"""

import os
import uuid
from flask import Flask, jsonify, request, send_from_directory
from flask_cors import CORS
from werkzeug.utils import secure_filename
from dotenv import load_dotenv
from routes.hostels import hostels_bp
from models import init_db
from routes.payment import payment_bp
from routes.panel import panel_bp

load_dotenv()

ALLOWED_IMAGE_EXTENSIONS = {"png", "jpg", "jpeg", "webp", "gif"}
MAX_IMAGE_SIZE_MB = 5


def allowed_image(filename):
    return (
        "." in filename
        and filename.rsplit(".", 1)[1].lower() in ALLOWED_IMAGE_EXTENSIONS
    )


def create_app():
    app = Flask(__name__)

    # -----------------------------------------------------------------------
    # Configuration
    # -----------------------------------------------------------------------
    app.config["SECRET_KEY"] = os.getenv("SECRET_KEY", "dwellr-dev-secret-change-in-prod")
    app.config["JSON_SORT_KEYS"] = False
    app.config["MAX_CONTENT_LENGTH"] = MAX_IMAGE_SIZE_MB * 1024 * 1024  # 5 MB hard limit

    UPLOAD_FOLDER = os.path.join(os.path.dirname(__file__), "static", "uploads")
    os.makedirs(UPLOAD_FOLDER, exist_ok=True)
    app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER

    # -----------------------------------------------------------------------
    # CORS — open to all origins so file://, VS Code Live Server,
    # localhost on any port, and production domains all work without
    # needing to whitelist every possible address.
    # Lock this down in production via the CORS_ORIGINS env variable.
    # -----------------------------------------------------------------------
    env = os.getenv("FLASK_ENV", "development")
    if env == "production":
        raw = os.getenv("CORS_ORIGINS", "")
        origins = [o.strip() for o in raw.split(",") if o.strip()] or ["*"]
        CORS(app, origins=origins, supports_credentials=True)
    else:
        # Development: allow everything, including file:// (origin: null)
        CORS(app, origins="*")

    # -----------------------------------------------------------------------
    # Register Blueprints
    # -----------------------------------------------------------------------
    app.register_blueprint(hostels_bp)
    app.register_blueprint(payment_bp)
    app.register_blueprint(panel_bp)

    # -----------------------------------------------------------------------
    # Auto-initialise database (create table + seed if empty)
    # -----------------------------------------------------------------------
    with app.app_context():
        try:
            init_db()
        except Exception as e:
            print(f"[Dwellr] WARNING: DB init failed — {e}")
            print("[Dwellr] Check your .env DB credentials and that PostgreSQL is running.")

    # -----------------------------------------------------------------------
    # Image Upload endpoint
    # POST /upload  — multipart/form-data, field name: "image"
    # Returns: { "success": true, "url": "http://localhost:5000/static/uploads/xyz.jpg" }
    # -----------------------------------------------------------------------
    @app.route("/upload", methods=["POST"])
    def upload_image():
        if "image" not in request.files:
            return jsonify({"success": False, "error": "No file field named 'image' in request."}), 400

        file = request.files["image"]

        if not file or file.filename == "":
            return jsonify({"success": False, "error": "No file was selected."}), 400

        if not allowed_image(file.filename):
            return jsonify({
                "success": False,
                "error": f"File type not allowed. Use: {', '.join(ALLOWED_IMAGE_EXTENSIONS)}."
            }), 415

        ext = file.filename.rsplit(".", 1)[1].lower()
        unique_name = f"{uuid.uuid4().hex}.{ext}"
        save_path = os.path.join(app.config["UPLOAD_FOLDER"], unique_name)
        file.save(save_path)

        port = os.getenv("PORT", 5000)
        file_url = f"http://localhost:{port}/static/uploads/{unique_name}"

        return jsonify({"success": True, "url": file_url}), 201

    # Serve uploaded images
    @app.route("/static/uploads/<path:filename>")
    def serve_upload(filename):
        return send_from_directory(app.config["UPLOAD_FOLDER"], filename)

    # -----------------------------------------------------------------------
    # Root & Health endpoints
    # -----------------------------------------------------------------------
    @app.route("/", methods=["GET"])
    def root():
        return jsonify({
            "service": "Dwellr API",
            "version": "2.0.0",
            "status": "running",
            "endpoints": {
                "GET    /hostels":          "List all hostels (?location=&price=&type=)",
                "GET    /hostels/<id>":     "Get single hostel",
                "POST   /hostels":          "Create new hostel (JSON)",
                "PUT    /hostels/<id>":     "Update hostel",
                "DELETE /hostels/<id>":     "Delete hostel",
                "POST   /upload":           "Upload image file → returns URL",
                "GET    /health":           "Health check",
            }
        }), 200

    @app.route("/health", methods=["GET"])
    def health():
        try:
            from models import get_db_connection
            conn = get_db_connection()
            conn.close()
            db_status = "connected"
        except Exception as e:
            db_status = f"error: {str(e)}"

        return jsonify({
            "status": "ok" if db_status == "connected" else "degraded",
            "database": db_status,
        }), 200 if db_status == "connected" else 503

    # -----------------------------------------------------------------------
    # Global error handlers
    # -----------------------------------------------------------------------
    @app.errorhandler(404)
    def not_found(e):
        return jsonify({"success": False, "error": "Endpoint not found."}), 404

    @app.errorhandler(405)
    def method_not_allowed(e):
        return jsonify({"success": False, "error": "Method not allowed."}), 405

    @app.errorhandler(413)
    def file_too_large(e):
        return jsonify({
            "success": False,
            "error": f"File exceeds the {MAX_IMAGE_SIZE_MB} MB size limit."
        }), 413

    @app.errorhandler(500)
    def internal_error(e):
        return jsonify({"success": False, "error": "An internal server error occurred."}), 500

    return app


# ---------------------------------------------------------------------------
# Run
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    app = create_app()
    debug = os.getenv("FLASK_DEBUG", "True").lower() in ("true", "1", "yes")
    port = int(os.getenv("PORT", 5000))
    app.run(debug=debug, port=port, host="0.0.0.0")
