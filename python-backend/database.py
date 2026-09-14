"""
SQLite database for the airline customer service demo.
Provides users and flight reservations seed data, plus helper query functions.
"""
import hashlib
import os
import secrets
import sqlite3

DEFAULT_DB_PATH = os.path.join(os.path.dirname(__file__), "airline.db")
SQLITE_TIMEOUT_SECONDS = 10


def get_database_path() -> str:
    return os.environ.get("AIRLINE_DB_PATH") or DEFAULT_DB_PATH


DB_PATH = get_database_path()


def get_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH, timeout=SQLITE_TIMEOUT_SECONDS)
    conn.execute(f"PRAGMA busy_timeout = {SQLITE_TIMEOUT_SECONDS * 1000}")
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    """Create tables and idempotently seed the demo data."""
    conn = get_connection()
    try:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS users (
                account_number TEXT PRIMARY KEY,
                name           TEXT NOT NULL,
                email          TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS reservations (
                confirmation_number TEXT PRIMARY KEY,
                account_number      TEXT NOT NULL REFERENCES users(account_number),
                flight_number       TEXT NOT NULL,
                airline             TEXT NOT NULL,
                departure_date      TEXT NOT NULL,   -- ISO-8601 date, e.g. 2026-06-15
                departure_airport   TEXT NOT NULL,   -- IATA code
                arrival_airport     TEXT NOT NULL,   -- IATA code
                seat_number         TEXT,
                status              TEXT NOT NULL DEFAULT 'confirmed'
            );

            CREATE TABLE IF NOT EXISTS credentials (
                username       TEXT PRIMARY KEY,
                account_number TEXT NOT NULL REFERENCES users(account_number),
                password_hash  TEXT NOT NULL,
                salt           TEXT NOT NULL
            );
        """)

        users = [
            ("11111111", "Alice Johnson",  "alice@example.com"),
            ("22222222", "Bob Smith",      "bob@example.com"),
            ("33333333", "Carol White",    "carol@example.com"),
            ("44444444", "David Brown",    "david@example.com"),
            ("55555555", "Eva Martinez",   "eva@example.com"),
        ]
        reservations = [
            # Alice - two bookings
            ("AA1234", "11111111", "DL-401",  "Delta",     "2026-06-15", "JFK", "LAX", "12A", "confirmed"),
            ("BB5678", "11111111", "UA-892",  "United",    "2026-07-20", "LAX", "ORD", "8C",  "confirmed"),
            # Bob - confirmed + cancelled
            ("CC9012", "22222222", "AA-215",  "American",  "2026-05-30", "BOS", "MIA", "22F", "confirmed"),
            ("DD3456", "22222222", "WN-1103", "Southwest", "2026-08-10", "MIA", "DFW", "15B", "cancelled"),
            # Carol - one booking
            ("EE7890", "33333333", "B6-421",  "JetBlue",   "2026-06-05", "JFK", "FLL", "4A",  "confirmed"),
            # David - two bookings
            ("FF1122", "44444444", "DL-789",  "Delta",     "2026-09-12", "ATL", "SEA", "30D", "confirmed"),
            ("GG3344", "44444444", "AA-560",  "American",  "2026-10-01", "SEA", "LAS", "18E", "confirmed"),
            # Eva - one booking
            ("HH5566", "55555555", "UA-237",  "United",    "2026-05-25", "SFO", "DEN", "11C", "confirmed"),
        ]
        demo_credentials = [
            ("alice", "11111111", "alice123"),
            ("bob",   "22222222", "bob123"),
            ("carol", "33333333", "carol123"),
            ("david", "44444444", "david123"),
            ("eva",   "55555555", "eva123"),
        ]

        with conn:
            conn.executemany(
                "INSERT INTO users VALUES (?, ?, ?) "
                "ON CONFLICT(account_number) DO NOTHING",
                users,
            )
            conn.executemany(
                "INSERT INTO reservations VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?) "
                "ON CONFLICT(confirmation_number) DO NOTHING",
                reservations,
            )
            for username, account_number, password in demo_credentials:
                salt = secrets.token_hex(16)
                pw_hash = _hash_password(password, salt)
                conn.execute(
                    "INSERT INTO credentials VALUES (?, ?, ?, ?) "
                    "ON CONFLICT(username) DO NOTHING",
                    (username, account_number, pw_hash, salt),
                )
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Password helpers
# ---------------------------------------------------------------------------

def _hash_password(password: str, salt: str) -> str:
    return hashlib.pbkdf2_hmac(
        "sha256", password.encode("utf-8"), salt.encode("utf-8"), 100_000
    ).hex()


def verify_credentials(username: str, password: str) -> dict | None:
    """Return user dict if credentials are valid, else None."""
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT c.account_number, c.password_hash, c.salt, u.name, u.email "
            "FROM credentials c JOIN users u USING (account_number) "
            "WHERE c.username = ?",
            (username.lower(),),
        ).fetchone()
    finally:
        conn.close()
    if not row:
        return None
    row = dict(row)
    expected = _hash_password(password, row["salt"])
    if not secrets.compare_digest(expected, row["password_hash"]):
        return None
    return {
        "username": username.lower(),
        "account_number": row["account_number"],
        "name": row["name"],
        "email": row["email"],
    }


# ---------------------------------------------------------------------------
# Query helpers
# ---------------------------------------------------------------------------

def get_user_by_account(account_number: str) -> dict | None:
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT * FROM users WHERE account_number = ?", (account_number,)
        ).fetchone()
    finally:
        conn.close()
    return dict(row) if row else None


def get_reservations_by_account(account_number: str) -> list[dict]:
    conn = get_connection()
    try:
        rows = conn.execute(
            "SELECT * FROM reservations WHERE account_number = ? ORDER BY departure_date",
            (account_number,),
        ).fetchall()
    finally:
        conn.close()
    return [dict(r) for r in rows]


def get_reservation_by_confirmation(confirmation_number: str) -> dict | None:
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT r.*, u.name AS passenger_name, u.email "
            "FROM reservations r JOIN users u USING (account_number) "
            "WHERE r.confirmation_number = ?",
            (confirmation_number.upper(),),
        ).fetchone()
    finally:
        conn.close()
    return dict(row) if row else None


def update_seat_in_db(confirmation_number: str, new_seat: str) -> bool:
    conn = get_connection()
    try:
        cur = conn.execute(
            "UPDATE reservations SET seat_number = ? WHERE confirmation_number = ?",
            (new_seat, confirmation_number.upper()),
        )
        conn.commit()
    finally:
        conn.close()
    return cur.rowcount > 0


def cancel_reservation_in_db(confirmation_number: str) -> bool:
    conn = get_connection()
    try:
        cur = conn.execute(
            "UPDATE reservations SET status = 'cancelled' WHERE confirmation_number = ?",
            (confirmation_number.upper(),),
        )
        conn.commit()
    finally:
        conn.close()
    return cur.rowcount > 0


# Initialise on import
init_db()
