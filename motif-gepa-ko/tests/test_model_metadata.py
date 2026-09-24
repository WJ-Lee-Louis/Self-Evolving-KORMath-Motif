"""The API wrapper records response metadata without copying the API key."""

import json
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest

from motif_gepa_ko.experiment import CountedLM
from motif_gepa_ko.model import MotifLM
from motif_gepa_ko.settings import Settings


class ModelMetadataTests(unittest.TestCase):
    def test_request_and_usage_are_logged_without_key(self):
        response = SimpleNamespace(
            id="completion-1", _request_id="request-1", model="motif/motif-3",
            created=123, system_fingerprint="fp", usage=SimpleNamespace(
                model_dump=lambda **_kwargs: {"prompt_tokens": 5, "completion_tokens": 3}
            ),
            choices=[SimpleNamespace(finish_reason="stop", message=SimpleNamespace(content="\uc815\ub2f5: 1"))],
        )
        client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(
            create=lambda **_kwargs: response,
        )))
        lm = MotifLM(Settings(api_key="private-key"), client=client)
        with TemporaryDirectory() as directory:
            path = Path(directory) / "api_requests.jsonl"
            counted = CountedLM(lm, 2, log_path=path, session_id="test-session")
            self.assertEqual(counted([{"role": "user", "content": "1+0?"}]), "\uc815\ub2f5: 1")
            record = json.loads(path.read_text(encoding="utf-8").strip())
            self.assertEqual(record["response_metadata"]["request_id"], "request-1")
            self.assertEqual(record["response_metadata"]["usage"]["prompt_tokens"], 5)
            self.assertNotIn("private-key", path.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
