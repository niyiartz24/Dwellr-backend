"""
Dwellr - Database Models & Connection
Handles PostgreSQL connection and hostel data access layer.
"""

import os
import secrets
import psycopg2
import psycopg2.extras
from dotenv import load_dotenv

load_dotenv()


def get_db_connection():
    """Create and return a PostgreSQL database connection."""
    conn = psycopg2.connect(
        host=os.getenv("DB_HOST", "localhost"),
        port=int(os.getenv("DB_PORT", 5432)),
        dbname=os.getenv("DB_NAME", "dwellr"),
        user=os.getenv("DB_USER", "postgres"),
        password=os.getenv("DB_PASSWORD", ""),
        cursor_factory=psycopg2.extras.RealDictCursor
    )
    return conn


def init_db():
    """
    Auto-create the hostels table if it does not exist, then seed it with
    demo data if the table is empty. Fully idempotent.
    """
    conn = get_db_connection()
    cur  = conn.cursor()

    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS hostels (
            id              SERIAL  PRIMARY KEY,
            name            TEXT    NOT NULL,
            location        TEXT    NOT NULL,
            price           INTEGER NOT NULL,
            description     TEXT    DEFAULT '',
            image_url       TEXT    DEFAULT '',
            contact         TEXT    DEFAULT '',
            amenities       TEXT[]  DEFAULT '{}',
            available_rooms INTEGER DEFAULT 0,
            hostel_type     TEXT    DEFAULT 'mixed',
            admin_token     TEXT    DEFAULT '',
            created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """
    )

    # Add admin_token column to existing tables that don't have it yet
    cur.execute("""
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_name='hostels' AND column_name='admin_token'
            ) THEN
                ALTER TABLE hostels ADD COLUMN admin_token TEXT DEFAULT '';
            END IF;
        END$$;
    """)

    cur.execute("SELECT COUNT(*) AS n FROM hostels;")
    row   = cur.fetchone()
    count = row["n"] if row else 0

    if count == 0:
        demo_token = secrets.token_urlsafe(24)
        seed_data = [
            (
                "Greenview Student Lodge", "Yaba, Lagos", 45000,
                "A well-maintained hostel close to UNILAG and Yaba College of Technology. "
                "Offers 24/7 security, constant water supply, and a clean communal kitchen.",
                "https://images.unsplash.com/photo-1555854877-bab0e564b8d5?w=800&q=80",
                "+2348012345678", ["WiFi","Security","Water Supply","Kitchen","Laundry"],
                12, "mixed", demo_token
            ),
            (
                "Summit Halls Residence", "Ojodu, Lagos", 38000,
                "Modern student accommodation with individual study desks and a shared lounge. "
                "Close to Lagos State University campus.",
                "https://images.unsplash.com/photo-1560448204-e02f11c3d0e2?w=800&q=80",
                "+2348023456789", ["WiFi","Security","Study Room","CCTV","Generator"],
                8, "female", demo_token
            ),
            (
                "Citadel Student Inn", "Surulere, Lagos", 52000,
                "Premium student accommodation with air-conditioned rooms, gym, and high-speed internet.",
                "https://images.unsplash.com/photo-1554995207-c18c203602cb?w=800&q=80",
                "+2348034567890", ["WiFi","AC","Gym","Security","Generator","Parking"],
                5, "mixed", secrets.token_urlsafe(24)
            ),
            (
                "Heritage House Ibadan", "Bodija, Ibadan", 28000,
                "Affordable student housing near University of Ibadan with 24-hour security.",
                "https://images.unsplash.com/photo-1522708323590-d24dbb6b0267?w=800&q=80",
                "+2348045678901", ["Security","Water Supply","Kitchen","Parking"],
                20, "male", secrets.token_urlsafe(24)
            ),
            (
                "Nova Student Suites", "Garki, Abuja", 65000,
                "Upscale self-contained suites in the FCT with private bathrooms and 24/7 power.",
                "https://images.unsplash.com/photo-1536376072261-38c75010e6c9?w=800&q=80",
                "+2348056789012", ["WiFi","AC","Security","Generator","Kitchen","CCTV","Water Supply"],
                3, "mixed", secrets.token_urlsafe(24)
            ),
            (
                "Scholars Den Enugu", "GRA, Enugu", 22000,
                "Budget-friendly accommodation near University of Nigeria Enugu Campus.",
                "https://images.unsplash.com/photo-1586023492125-27b2c045efd7?w=800&q=80",
                "+2348067890123", ["Security","Water Supply","Kitchen"],
                18, "mixed", secrets.token_urlsafe(24)
            ),
        ]
        cur.executemany(
            """
            INSERT INTO hostels
                (name, location, price, description, image_url, contact,
                 amenities, available_rooms, hostel_type, admin_token)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
            """,
            seed_data
        )
        print(f"[Dwellr] Database initialised with {len(seed_data)} demo listings.")
    else:
        print(f"[Dwellr] Database ready — {count} listing(s) found.")

    conn.commit()
    cur.close()
    conn.close()


# ---------------------------------------------------------------------------
# Token helpers
# ---------------------------------------------------------------------------

def get_or_create_token_for_contact(contact: str) -> str:
    """
    If this contact number already has listings, reuse their existing token
    so all their properties are accessible from one panel.
    Otherwise generate a fresh token.
    """
    conn = get_db_connection()
    cur  = conn.cursor()
    cur.execute(
        "SELECT admin_token FROM hostels WHERE contact = %s AND admin_token != '' LIMIT 1",
        (contact,)
    )
    row = cur.fetchone()
    cur.close()
    conn.close()
    if row and row["admin_token"]:
        return row["admin_token"]
    return secrets.token_urlsafe(24)


def get_hostels_by_token(token: str):
    """Return all hostels belonging to an agent token."""
    conn = get_db_connection()
    cur  = conn.cursor()
    cur.execute(
        "SELECT * FROM hostels WHERE admin_token = %s ORDER BY created_at DESC",
        (token,)
    )
    rows = cur.fetchall()
    cur.close()
    conn.close()
    return [dict(r) for r in rows]


def token_owns_hostel(token: str, hostel_id: int) -> bool:
    """Check that a token actually owns the given hostel."""
    conn = get_db_connection()
    cur  = conn.cursor()
    cur.execute(
        "SELECT id FROM hostels WHERE id = %s AND admin_token = %s",
        (hostel_id, token)
    )
    row = cur.fetchone()
    cur.close()
    conn.close()
    return row is not None


# ---------------------------------------------------------------------------
# Standard CRUD
# ---------------------------------------------------------------------------

def get_all_hostels(location=None, max_price=None, hostel_type=None):
    conn = get_db_connection()
    cur  = conn.cursor()

    query  = "SELECT * FROM hostels WHERE 1=1"
    params = []

    if location:
        query += " AND LOWER(location) LIKE LOWER(%s)"
        params.append(f"%{location}%")

    if max_price:
        try:
            query += " AND price <= %s"
            params.append(int(max_price))
        except ValueError:
            pass

    if hostel_type and hostel_type in ("male", "female", "mixed"):
        query += " AND hostel_type = %s"
        params.append(hostel_type)

    query += " ORDER BY created_at DESC"
    cur.execute(query, params)
    rows = cur.fetchall()
    cur.close()
    conn.close()
    return [dict(r) for r in rows]


def get_hostel_by_id(hostel_id):
    conn = get_db_connection()
    cur  = conn.cursor()
    cur.execute("SELECT * FROM hostels WHERE id = %s", (hostel_id,))
    row = cur.fetchone()
    cur.close()
    conn.close()
    return dict(row) if row else None


def create_hostel(data):
    conn = get_db_connection()
    cur  = conn.cursor()

    amenities = data.get("amenities", [])
    if isinstance(amenities, str):
        amenities = [a.strip() for a in amenities.split(",") if a.strip()]

    # Get or create token for this agent based on their contact number
    contact = data.get("contact", "").strip()
    token   = get_or_create_token_for_contact(contact) if contact else secrets.token_urlsafe(24)

    cur.execute(
        """
        INSERT INTO hostels
            (name, location, price, description, image_url, contact,
             amenities, available_rooms, hostel_type, admin_token)
        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
        RETURNING *
        """,
        (
            data["name"],
            data["location"],
            int(data["price"]),
            data.get("description", ""),
            data.get("image_url", ""),
            contact,
            amenities,
            int(data.get("available_rooms", 0)),
            data.get("hostel_type", "mixed"),
            token,
        )
    )

    new_hostel = dict(cur.fetchone())
    conn.commit()
    cur.close()
    conn.close()
    return new_hostel


def update_hostel(hostel_id, data):
    conn = get_db_connection()
    cur  = conn.cursor()

    fields = []
    params = []

    updatable = ["name","location","price","description","image_url",
                 "contact","available_rooms","hostel_type"]
    for field in updatable:
        if field in data:
            fields.append(f"{field} = %s")
            val = data[field]
            if field in ("price", "available_rooms"):
                val = int(val)
            params.append(val)

    if "amenities" in data:
        amenities = data["amenities"]
        if isinstance(amenities, str):
            amenities = [a.strip() for a in amenities.split(",") if a.strip()]
        fields.append("amenities = %s")
        params.append(amenities)

    if not fields:
        cur.close()
        conn.close()
        return get_hostel_by_id(hostel_id)

    params.append(hostel_id)
    cur.execute(
        f"UPDATE hostels SET {', '.join(fields)} WHERE id = %s RETURNING *",
        params
    )
    row = cur.fetchone()
    conn.commit()
    cur.close()
    conn.close()
    return dict(row) if row else None


def delete_hostel(hostel_id):
    conn = get_db_connection()
    cur  = conn.cursor()
    cur.execute("DELETE FROM hostels WHERE id = %s RETURNING id", (hostel_id,))
    deleted = cur.fetchone()
    conn.commit()
    cur.close()
    conn.close()
    return deleted is not None
