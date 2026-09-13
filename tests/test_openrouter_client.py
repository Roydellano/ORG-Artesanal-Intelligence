import io
import json
import unittest
from unittest.mock import patch
from urllib.error import HTTPError

from openrouter_client import OpenRouterError, chat


class OpenRouterClientTests(unittest.TestCase):
    def setUp(self):
        env = patch.dict("openrouter_client.os.environ", {}, clear=True)
        config = patch("openrouter_client.dotenv_values", return_value={
            "OPENROUTER_API_KEY": "test-secret",
            "OPENROUTER_MODEL": "deepseek/deepseek-v4.1-flash",
        })
        env.start()
        config.start()
        self.addCleanup(env.stop)
        self.addCleanup(config.stop)

    @patch("openrouter_client.urlopen")
    def test_configured_model_and_environment_override(self, send):
        send.return_value = io.BytesIO(json.dumps({"choices": [{
            "finish_reason": "stop", "message": {"content": "OK"}
        }]}).encode())
        with patch.dict("openrouter_client.os.environ", {"OPENROUTER_MODEL": "other/model"}):
            self.assertEqual(chat([{"role": "user", "content": "hello"}]), "OK")
        request = send.call_args.args[0]
        self.assertEqual(json.loads(request.data)["model"], "other/model")
        self.assertEqual(request.get_header("Authorization"), "Bearer test-secret")
        self.assertEqual(send.call_args.kwargs["timeout"], 60)

    @patch("openrouter_client.urlopen")
    def test_missing_key_never_calls_network(self, send):
        with patch.dict("openrouter_client.os.environ", {"OPENROUTER_API_KEY": ""}):
            with self.assertRaises(OpenRouterError):
                chat([{"role": "user", "content": "hello"}])
        send.assert_not_called()

    @patch("openrouter_client.urlopen")
    def test_provider_errors_do_not_expose_body(self, send):
        send.side_effect = HTTPError("https://openrouter.ai", 401, "test-secret", {}, None)
        with self.assertRaises(OpenRouterError) as result:
            chat([{"role": "user", "content": "hello"}])
        self.assertIn("401", str(result.exception))
        self.assertNotIn("test-secret", str(result.exception))

    @patch("openrouter_client.urlopen")
    def test_rejects_invalid_and_truncated_responses(self, send):
        for body in [b"invalid", b'{}', b'{"choices":[{"finish_reason":"length","message":{"content":"partial"}}]}']:
            with self.subTest(body=body):
                send.return_value = io.BytesIO(body)
                with self.assertRaises(OpenRouterError):
                    chat([{"role": "user", "content": "hello"}])

    @patch("openrouter_client.urlopen")
    def test_zdr_toggle_allows_free_models_and_fallback_routing(self, send):
        send.side_effect = lambda *a, **k: io.BytesIO(json.dumps({"choices": [{
            "finish_reason": "stop", "message": {"content": "OK"}
        }]}).encode())
        # With default ZDR (on), free model without synthetic=True is rejected
        with patch.dict("openrouter_client.os.environ", {"OPENROUTER_MODEL": "test:free", "OPENROUTER_ZDR": "on"}):
            with self.assertRaises(OpenRouterError):
                chat([{"role": "user", "content": "hello"}], synthetic=False)

        # With ZDR toggled off, free model is allowed and provider routing allows fallbacks
        with patch.dict("openrouter_client.os.environ", {"OPENROUTER_MODEL": "test:free", "OPENROUTER_ZDR": "off"}):
            result = chat([{"role": "user", "content": "hello"}], synthetic=False)
            self.assertEqual(result, "OK")
            req = json.loads(send.call_args.args[0].data)
            self.assertEqual(req["provider"], {"allow_fallbacks": True})

        # Explicit zdr=False param also allows it
        with patch.dict("openrouter_client.os.environ", {"OPENROUTER_MODEL": "test:free", "OPENROUTER_ZDR": "on"}):
            result = chat([{"role": "user", "content": "hello"}], synthetic=False, zdr=False)
            self.assertEqual(result, "OK")


if __name__ == "__main__":
    unittest.main()
