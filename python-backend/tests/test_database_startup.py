"""Verify database recovery through the actual FastAPI startup lifecycle."""
import tempfile
import unittest
from contextlib import closing
from pathlib import Path
from unittest.mock import patch

from test_chat_content_filter import _get_api_module


class DatabaseStartupTests(unittest.TestCase):
    def test_restart_restores_missing_data_and_preserves_booking_changes(self):
        api = _get_api_module()
        import database
        from fastapi.testclient import TestClient

        with tempfile.TemporaryDirectory() as directory, patch.object(
            database, "DB_PATH", str(Path(directory) / "airline.db")
        ):
            # The app is already imported; startup must create this missing DB.
            with TestClient(api.app) as client:
                for username, password in (
                    ("john@google.com", "user2"),
                    ("alice@johnson.com", "alice123"),
                ):
                    response = client.post("/login", json={
                        "username": username, "password": password,
                    })
                    self.assertEqual(response.status_code, 200)
                    self.assertEqual(response.json()["email"], username)
                database.update_seat_in_db("JJ7788", "9C")
                database.cancel_reservation_in_db("LL2233")

            with closing(database.get_connection()) as conn:
                conn.execute("DELETE FROM credentials WHERE username = 'john@google.com'")
                conn.execute("DELETE FROM reservations WHERE confirmation_number = 'KK9900'")
                conn.commit()

            with TestClient(api.app) as client:
                response = client.post("/login", json={
                    "username": "john@google.com", "password": "user2",
                })
                self.assertEqual(response.status_code, 200)
                self.assertIsNotNone(database.get_reservation_by_confirmation("KK9900"))
                self.assertEqual(database.get_reservation_by_confirmation("JJ7788")["seat_number"], "9C")
                self.assertEqual(database.get_reservation_by_confirmation("LL2233")["status"], "cancelled")


if __name__ == "__main__":
    unittest.main()
