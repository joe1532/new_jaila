import sys
import unittest
from pathlib import Path

ENGINE_DIR = Path(__file__).resolve().parents[1] / "lovhistorik"
if str(ENGINE_DIR) not in sys.path:
    sys.path.insert(0, str(ENGINE_DIR))

import lex_dania  # noqa: E402


NOTES_XML = """\
<root>
  <Linea>Bemærkninger til lovforslagets enkelte bestemmelser</Linea>
  <Linea>Til § 1</Linea>
  <Linea>Til nr. 1</Linea>
  <Linea>Første afsnit om forslaget.</Linea>
  <Linea>Andet afsnit om baggrunden.</Linea>
</root>
""".encode("utf-8")


class ExplanatoryNotesTests(unittest.TestCase):
    def test_keeps_linea_as_separate_paragraphs(self):
        notes = lex_dania.extract_explanatory_notes(NOTES_XML)
        text = notes[(1, 1)]
        self.assertEqual(
            text,
            "Første afsnit om forslaget.\n\nAndet afsnit om baggrunden.",
        )
        self.assertNotIn("forslaget. Andet", text)
