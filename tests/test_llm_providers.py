import unittest

from backend.services.llm_providers import format_history_prefix, normalize_chat_provider, with_history
from backend.services.openai_service import cache_fields_for_model


class LlmProviderTests(unittest.TestCase):
    def test_normalize_accepts_openai_and_grok(self):
        self.assertEqual(normalize_chat_provider(None), "openai")
        self.assertEqual(normalize_chat_provider("GROK"), "grok")
        with self.assertRaises(ValueError):
            normalize_chat_provider("claude")

    def test_history_keeps_last_turns_and_skips_system(self):
        prefix = format_history_prefix(
            [
                {"role": "system", "text": "skjul"},
                {"role": "user", "text": "første"},
                {"role": "assistant", "text": "svar"},
                {"role": "user", "text": "opfølgning"},
            ]
        )
        self.assertIn("Bruger:\nførste", prefix)
        self.assertIn("Assistent:\nsvar", prefix)
        self.assertNotIn("skjul", prefix)
        self.assertTrue(prefix.startswith("[Tidligere samtale]"))

    def test_with_history_joins_or_passes_through(self):
        self.assertEqual(with_history("", "hej"), "hej")
        self.assertEqual(with_history("hist", ""), "hist")
        self.assertIn("\n\n", with_history("hist", "hej"))

    def test_grok_does_not_get_openai_cache_retention(self):
        self.assertEqual(cache_fields_for_model("grok-4.6"), {})
        self.assertIn("prompt_cache_retention", cache_fields_for_model("gpt-5.2"))


if __name__ == "__main__":
    unittest.main()
