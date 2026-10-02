"""Exercise the merged Azure API through HTTP without calling a model."""
import unittest
import json
from datetime import datetime
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


class AzureToolStreamingTests(unittest.IsolatedAsyncioTestCase):
    async def test_tool_enabled_agent_sends_no_reasoning_and_finishes_chatkit_stream(self):
        _get_api_module()
        import server
        from test_chat_content_filter import httpx
        from agents import OpenAIChatCompletionsModel
        from openai import AsyncAzureOpenAI
        from chatkit.types import InferenceOptions, UserMessageItem, UserMessageTextContent

        def model_response(request):
            body = json.loads(request.content)
            # Reproduce the provider's rejection unless the wire request is compatible.
            if body.get("reasoning_effort") != "none" or not body.get("tools"):
                return httpx.Response(400, json={"error": {
                    "message": "Function tools require reasoning_effort=none",
                    "type": "invalid_request_error",
                }})
            chunks = [
                {"delta": {"role": "assistant", "content": "Hello!"}, "finish_reason": None},
                {"delta": {}, "finish_reason": "stop"},
            ]
            data = "".join("data: " + json.dumps({
                "id": "chatcmpl_test", "object": "chat.completion.chunk",
                "created": 1, "model": "test-model", "choices": [{"index": 0, **chunk}],
            }) + "\n\n" for chunk in chunks) + "data: [DONE]\n\n"
            return httpx.Response(200, text=data, headers={"Content-Type": "text/event-stream"})

        async with httpx.AsyncClient(transport=httpx.MockTransport(model_response)) as http_client:
            client = AsyncAzureOpenAI(
                api_key="test-key", azure_endpoint="https://test.openai.azure.com",
                api_version="2025-01-01-preview", http_client=http_client,
            )
            agent = server.triage_agent.clone(
                model=OpenAIChatCompletionsModel(model="test-model", openai_client=client),
                input_guardrails=[], handoffs=[],
            )
            chat_server = server.AirlineServer()
            thread = await chat_server.ensure_thread(None, {})
            message = UserMessageItem(
                id="msg_test", thread_id=thread.id, created_at=datetime.now(),
                content=[UserMessageTextContent(text="Hello")], attachments=[],
                inference_options=InferenceOptions(),
            )
            with patch.object(server, "_get_agent_by_name", return_value=agent):
                events = [event async for event in chat_server.respond(thread, message, {})]

        replies = [event.item for event in events
                   if event.type == "thread.item.done" and event.item.type == "assistant_message"]
        self.assertEqual(len(replies), 1)
        self.assertEqual(replies[0].content[0].text, "Hello!")


if __name__ == "__main__":
    unittest.main()
