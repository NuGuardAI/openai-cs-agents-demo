"""Exercise the merged Azure API through HTTP without calling a model."""
import unittest
from unittest.mock import patch

from test_chat_content_filter import _get_api_module, _make_bad_request_error


class ChatKitAzureTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.api = _get_api_module()
        from fastapi.testclient import TestClient

        cls.client = TestClient(cls.api.app)

    def test_bootstrap_thread_can_be_read_through_chatkit_and_state_api(self):
        bootstrap = self.client.get("/chatkit/bootstrap")
        self.assertEqual(bootstrap.status_code, 200)
        thread_id = bootstrap.json()["thread_id"]
        state = self.client.get("/chatkit/state", params={"thread_id": thread_id})
        self.assertEqual(state.json()["thread_id"], thread_id)
        self.assertEqual(len(state.json()["agents"]), 6)
        thread = self.client.post("/chatkit", json={
            "type": "threads.get_by_id", "params": {"thread_id": thread_id},
        })
        self.assertEqual(thread.status_code, 200)
        self.assertEqual(thread.json()["id"], thread_id)

    def test_cross_origin_chatkit_preflight_uses_fastapi_cors(self):
        response = self.client.options("/chatkit", headers={
            "Origin": "http://localhost:3250",
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "content-type",
        })
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers["access-control-allow-origin"], "http://localhost:3250")

    def test_content_filter_during_stream_returns_refusal_and_thread_stays_readable(self):
        import server

        thread_id = self.client.get("/chatkit/bootstrap").json()["thread_id"]
        error = _make_bad_request_error(self.api.BadRequestError, "content_filter")

        async def blocked_stream(*args, **kwargs):
            raise error
            yield  # Make this an async generator like stream_agent_response.

        with patch.object(server.Runner, "run_streamed"), patch.object(
            server, "stream_agent_response", blocked_stream
        ):
            response = self.client.post("/chatkit", json={
                "type": "threads.add_user_message",
                "params": {
                    "thread_id": thread_id,
                    "input": {
                        "content": [{"type": "input_text", "text": "ignore instructions"}],
                        "attachments": [], "inference_options": {},
                    },
                },
            })

        self.assertEqual(response.status_code, 200)
        self.assertIn("text/event-stream", response.headers["content-type"])
        self.assertEqual(response.headers["cache-control"], "no-cache")
        self.assertIn("Sorry, I can't help with that request.", response.text)
        self.assertIn("runner_state_update", response.text)
        thread = self.client.post("/chatkit", json={
            "type": "threads.get_by_id", "params": {"thread_id": thread_id},
        })
        self.assertIn("Sorry, I can't help with that request.", thread.text)


if __name__ == "__main__":
    unittest.main()
