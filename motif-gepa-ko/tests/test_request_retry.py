"""A stalled model call is retried visibly without turning into a math score."""

import asyncio
import httpx
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from openai import BadRequestError, InternalServerError

from motif_gepa_ko.experiment import CountedLM, _retryable_model_error
from motif_gepa_ko.model import MotifLM, RequestDeadlineExceeded
from motif_gepa_ko.settings import Settings


class RetryTests(unittest.TestCase):
    def test_provider_500_retries_but_bad_request_does_not(self):
        request = httpx.Request("POST", "https://llm.onerouter.pro/v1/chat/completions")
        server_response = httpx.Response(500, request=request)
        bad_response = httpx.Response(400, request=request)
        self.assertTrue(_retryable_model_error(
            InternalServerError("generation_error", response=server_response, body=None)
        ))
        self.assertFalse(_retryable_model_error(
            BadRequestError("invalid request", response=bad_response, body=None)
        ))

    def test_real_client_path_has_total_deadline_and_no_hidden_sdk_retries(self):
        options = []

        class StalledClient:
            def __init__(self, **kwargs):
                options.append(kwargs)
                self.chat = SimpleNamespace(completions=SimpleNamespace(create=self.create))

            async def __aenter__(self):
                return self

            async def __aexit__(self, *_args):
                return None

            async def create(self, **_kwargs):
                await asyncio.sleep(0.1)

        with patch("motif_gepa_ko.model.AsyncOpenAI", StalledClient):
            lm = MotifLM(Settings(api_key="private-key", timeout_seconds=0.01))
            with self.assertRaises(RequestDeadlineExceeded):
                lm([{"role": "user", "content": "Question"}])
        self.assertEqual(options[0]["max_retries"], 0)
        self.assertEqual(options[0]["timeout"], 0.01)

    def test_two_timeouts_then_success_are_recorded_as_one_logical_call(self):
        class FakeModel:
            settings = Settings(api_key="private-key", timeout_seconds=0.1, max_attempts=3)
            last_response_metadata = {"response_id": "response-3"}

            def __init__(self):
                self.calls = 0

            def __call__(self, _prompt):
                self.calls += 1
                if self.calls < 3:
                    raise RequestDeadlineExceeded("stalled")
                return "FINAL_ANSWER: 42"

        with TemporaryDirectory() as directory, patch("motif_gepa_ko.experiment.time.sleep"):
            path = Path(directory) / "api_requests.jsonl"
            model = FakeModel()
            lm = CountedLM(model, 10, log_path=path, session_id="retry-test")
            self.assertEqual(lm([{"role": "user", "content": "Question"}]), "FINAL_ANSWER: 42")
            self.assertEqual((lm.calls, lm.provider_calls, model.calls), (1, 3, 3))
            request = json.loads(path.read_text(encoding="utf-8").strip())
            self.assertEqual((request["status"], request["provider_attempts"]), ("success", 3))
            attempts = [json.loads(line) for line in
                        (Path(directory) / "api_attempts.jsonl").read_text(encoding="utf-8").splitlines()]
            self.assertEqual([row["event"] for row in attempts],
                             ["started", "error", "started", "error", "started", "success"])
            self.assertNotIn("private-key", path.read_text(encoding="utf-8"))

    def test_exhausted_timeouts_raise_and_are_not_scored(self):
        class StalledModel:
            settings = Settings(api_key="private-key", max_attempts=2)
            last_response_metadata = None

            def __call__(self, _prompt):
                raise RequestDeadlineExceeded("stalled")

        with TemporaryDirectory() as directory, patch("motif_gepa_ko.experiment.time.sleep"):
            path = Path(directory) / "api_requests.jsonl"
            lm = CountedLM(StalledModel(), 10, log_path=path)
            with self.assertRaises(RequestDeadlineExceeded):
                lm("Reflect")
            request = json.loads(path.read_text(encoding="utf-8").strip())
            self.assertEqual((request["status"], request["provider_attempts"]), ("error", 2))
            self.assertEqual(lm.provider_calls, 2)


if __name__ == "__main__":
    unittest.main()
