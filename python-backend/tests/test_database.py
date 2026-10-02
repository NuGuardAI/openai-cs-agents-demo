import importlib
import multiprocessing
import os
from pathlib import Path
import sqlite3
import sys
import tempfile
import threading
import time
import unittest
from contextlib import closing


BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))


def initialize_database(database_path: str, start_event) -> None:
    os.environ["AIRLINE_DB_PATH"] = database_path
    start_event.wait()
    import database  # noqa: F401


class DatabaseInitializationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.database_path = str(Path(self.temporary_directory.name) / "airline.db")
        self.original_database_path = os.environ.get("AIRLINE_DB_PATH")
        os.environ["AIRLINE_DB_PATH"] = self.database_path
        self.database = importlib.reload(importlib.import_module("database"))

    def tearDown(self) -> None:
        if self.original_database_path is None:
            os.environ.pop("AIRLINE_DB_PATH", None)
        else:
            os.environ["AIRLINE_DB_PATH"] = self.original_database_path
        self.temporary_directory.cleanup()

    def test_reinitialization_preserves_data_and_authentication(self) -> None:
        with closing(sqlite3.connect(self.database_path)) as conn:
            original_password_hash = conn.execute(
                "SELECT password_hash FROM credentials WHERE username = 'alice'"
            ).fetchone()[0]

        self.assertTrue(self.database.update_seat_in_db("AA1234", "23A"))
        self.assertTrue(self.database.cancel_reservation_in_db("CC9012"))
        self.database.init_db()

        with closing(sqlite3.connect(self.database_path)) as conn:
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM users").fetchone()[0], 7)
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM reservations").fetchone()[0], 12)
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM credentials").fetchone()[0], 7)
            self.assertEqual(
                conn.execute(
                    "SELECT password_hash FROM credentials WHERE username = 'alice'"
                ).fetchone()[0],
                original_password_hash,
            )
            self.assertEqual(
                conn.execute(
                    "SELECT seat_number FROM reservations WHERE confirmation_number = 'AA1234'"
                ).fetchone()[0],
                "23A",
            )
            self.assertEqual(
                conn.execute(
                    "SELECT status FROM reservations WHERE confirmation_number = 'CC9012'"
                ).fetchone()[0],
                "cancelled",
            )

        for username, password in (
            ("alice", "alice123"),
            ("bob", "bob123"),
            ("carol", "carol123"),
            ("david", "david123"),
            ("eva", "eva123"),
            ("john@google.com", "user2"),
            ("alice@johnson.com", "alice123"),
        ):
            self.assertIsNotNone(self.database.verify_credentials(username, password))

    def test_initialization_completes_a_partial_database_without_overwriting(self) -> None:
        with closing(sqlite3.connect(self.database_path)) as conn:
            conn.execute("UPDATE users SET name = 'Existing Alice' WHERE account_number = '11111111'")
            conn.execute("DELETE FROM credentials WHERE username != 'alice'")
            conn.execute("DELETE FROM reservations WHERE confirmation_number != 'AA1234'")
            conn.execute("DELETE FROM users WHERE account_number != '11111111'")
            conn.commit()

        self.database.init_db()

        with closing(sqlite3.connect(self.database_path)) as conn:
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM users").fetchone()[0], 7)
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM reservations").fetchone()[0], 12)
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM credentials").fetchone()[0], 7)
            self.assertEqual(
                conn.execute(
                    "SELECT name FROM users WHERE account_number = '11111111'"
                ).fetchone()[0],
                "Existing Alice",
            )
            self.assertEqual(
                conn.execute(
                    "SELECT COUNT(*) FROM reservations r "
                    "LEFT JOIN users u USING (account_number) "
                    "WHERE u.account_number IS NULL"
                ).fetchone()[0],
                0,
            )

    def test_email_logins_have_distinct_profiles_and_bookings(self) -> None:
        john = self.database.verify_credentials("john@google.com", "user2")
        alice = self.database.verify_credentials("alice@johnson.com", "alice123")
        self.assertIsNotNone(john)
        self.assertIsNotNone(alice)
        for field in ("account_number", "name", "email"):
            self.assertNotEqual(john[field], alice[field])
        self.assertEqual(john["email"], "john@google.com")
        self.assertEqual(alice["email"], "alice@johnson.com")
        john_bookings = self.database.get_reservations_by_account(john["account_number"])
        alice_bookings = self.database.get_reservations_by_account(alice["account_number"])
        self.assertEqual(len(john_bookings), 2)
        self.assertEqual(len(alice_bookings), 2)
        for field in ("confirmation_number", "flight_number", "departure_date",
                      "departure_airport", "arrival_airport", "seat_number"):
            self.assertTrue(
                {booking[field] for booking in john_bookings}.isdisjoint(
                    {booking[field] for booking in alice_bookings}
                ), field,
            )
        self.assertIsNone(self.database.verify_credentials("john@google.com", "alice123"))
        self.assertIsNone(self.database.verify_credentials("alice@johnson.com", "user2"))

    def test_database_path_configuration(self) -> None:
        self.assertEqual(self.database.get_database_path(), self.database_path)

        original_database_path = os.environ.pop("AIRLINE_DB_PATH")
        try:
            self.assertEqual(
                self.database.get_database_path(), self.database.DEFAULT_DB_PATH
            )
            os.environ["AIRLINE_DB_PATH"] = ""
            self.assertEqual(
                self.database.get_database_path(), self.database.DEFAULT_DB_PATH
            )
        finally:
            os.environ["AIRLINE_DB_PATH"] = original_database_path

    def test_initialization_waits_for_a_short_lived_write_lock(self) -> None:
        lock_connection = sqlite3.connect(self.database_path, check_same_thread=False)
        lock_connection.execute("BEGIN EXCLUSIVE")
        release_lock = threading.Timer(0.1, lock_connection.commit)
        release_lock.start()
        try:
            self.database.init_db()
        finally:
            release_lock.join()
            lock_connection.close()

    def test_initialization_raises_when_lock_exceeds_timeout(self) -> None:
        original_timeout = self.database.SQLITE_TIMEOUT_SECONDS
        self.database.SQLITE_TIMEOUT_SECONDS = 0.1
        lock_connection = sqlite3.connect(self.database_path)
        lock_connection.execute("BEGIN EXCLUSIVE")
        try:
            start_time = time.monotonic()
            with self.assertRaises(sqlite3.OperationalError):
                self.database.init_db()
            self.assertGreaterEqual(time.monotonic() - start_time, 0.08)
        finally:
            lock_connection.rollback()
            lock_connection.close()
            self.database.SQLITE_TIMEOUT_SECONDS = original_timeout

    def test_concurrent_initializers_seed_one_consistent_database(self) -> None:
        concurrent_database_path = str(
            Path(self.temporary_directory.name) / "concurrent-airline.db"
        )
        context = multiprocessing.get_context("spawn")
        start_event = context.Event()
        processes = [
            context.Process(
                target=initialize_database,
                args=(concurrent_database_path, start_event),
            )
            for _ in range(4)
        ]

        for process in processes:
            process.start()
        start_event.set()
        for process in processes:
            process.join(timeout=30)
            self.assertFalse(process.is_alive())
            self.assertEqual(process.exitcode, 0)

        with closing(sqlite3.connect(concurrent_database_path)) as conn:
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM users").fetchone()[0], 7)
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM reservations").fetchone()[0], 12)
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM credentials").fetchone()[0], 7)


if __name__ == "__main__":
    unittest.main()