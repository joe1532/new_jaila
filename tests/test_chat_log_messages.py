import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from backend.services import chat_logs


class ChatLogPerMessageCitationsTests(unittest.TestCase):
    def test_keeps_citations_on_each_assistant_message(self):
        with TemporaryDirectory() as tmp:
            with (
                patch.object(chat_logs, "ANALYSE_LOGS_DIR", Path(tmp)),
                patch.object(chat_logs, "_generate_title_from_messages", return_value="Titel"),
            ):
                chat_logs.save_chat_log(
                    username="jonas",
                    session_id="sess-1",
                    used_model="gpt-test",
                    citations=[{"file_id": "b", "filename": "anden.pdf"}],
                    messages=[
                        {"role": "user", "text": "Første spørgsmål"},
                        {
                            "role": "assistant",
                            "text": "Første svar",
                            "citations": [{"file_id": "a", "filename": "første.pdf"}],
                            "used_retrieval_results": [
                                {
                                    "file_id": "a",
                                    "filename": "første.pdf",
                                    "text": "uddrag 1",
                                }
                            ],
                        },
                        {"role": "user", "text": "Opfølgning"},
                        {
                            "role": "assistant",
                            "text": "Andet svar",
                            "citations": [{"file_id": "b", "filename": "anden.pdf"}],
                            "used_retrieval_results": [
                                {
                                    "file_id": "b",
                                    "filename": "anden.pdf",
                                    "text": "uddrag 2",
                                }
                            ],
                        },
                    ],
                )
                listed = chat_logs.list_chat_logs("jonas")
                entry = chat_logs.get_chat_log("jonas", listed[0]["id"])
                self.assertIsNotNone(entry)
                assistants = [msg for msg in entry["messages"] if msg["role"] == "assistant"]
                self.assertEqual(assistants[0]["citations"][0]["filename"], "første.pdf")
                self.assertEqual(
                    assistants[0]["used_retrieval_results"][0]["text"],
                    "uddrag 1",
                )
                self.assertEqual(assistants[1]["citations"][0]["filename"], "anden.pdf")
                self.assertEqual(entry["citations"][0]["filename"], "anden.pdf")


    def test_keeps_pipeline_diagnostics(self):
        with TemporaryDirectory() as tmp:
            with (
                patch.object(chat_logs, "ANALYSE_LOGS_DIR", Path(tmp)),
                patch.object(chat_logs, "_generate_title_from_messages", return_value="Titel"),
            ):
                chat_logs.save_chat_log(
                    username="jonas",
                    session_id="sess-trace",
                    used_model="gpt-test",
                    messages=[
                        {"role": "user", "text": "Firmabil?"},
                        {"role": "assistant", "text": "Ja, stk. 4."},
                    ],
                    retrieval_diagnostics={
                        "pipeline": "task_critic_v1",
                        "pipeline_outcome": "godkend_draft",
                        "pipeline_trace": [
                            {"id": "critic", "title": "4. Kritik", "detail": "status=godkend"}
                        ],
                    },
                )
                listed = chat_logs.list_chat_logs("jonas")
                entry = chat_logs.get_chat_log("jonas", listed[0]["id"])
                self.assertIsNotNone(entry)
                self.assertEqual(entry["retrieval_diagnostics"]["pipeline"], "task_critic_v1")
                self.assertEqual(entry["retrieval_diagnostics"]["pipeline_outcome"], "godkend_draft")
