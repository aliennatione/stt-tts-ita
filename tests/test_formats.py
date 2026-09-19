"""Test per parsing timestamp e serializzazione formati (stdlib unittest)."""

import json
import unittest

from stt_tts_ita.formats import to_srt, to_txt, to_vtt
from stt_tts_ita.transcribe import Segment, Transcript, parse_timestamp


class TestTimestamp(unittest.TestCase):
    def test_parse_comma(self):
        self.assertAlmostEqual(parse_timestamp("00:00:08,820"), 8.82)

    def test_parse_dot(self):
        self.assertAlmostEqual(parse_timestamp("01:02:03.500"), 3723.5)

    def test_parse_invalid(self):
        self.assertEqual(parse_timestamp("n/a"), 0.0)


class TestFormats(unittest.TestCase):
    def setUp(self):
        self.tr = Transcript(
            segments=[
                Segment(0.0, 1.5, "Ciao mondo"),
                Segment(2.0, 4.25, "Seconda riga"),
            ],
            language="it",
        )

    def test_srt(self):
        srt = to_srt(self.tr)
        self.assertIn("00:00:00,000 --> 00:00:01,500", srt)
        self.assertIn("Ciao mondo", srt)
        self.assertIn("00:00:02,000 --> 00:00:04,250", srt)

    def test_vtt(self):
        vtt = to_vtt(self.tr)
        self.assertTrue(vtt.startswith("WEBVTT"))
        self.assertIn("00:00:01.500", vtt)

    def test_txt_with_timestamps(self):
        txt = to_txt(self.tr, with_timestamps=True)
        self.assertIn("[00:00:00,000 --> 00:00:01,500] Ciao mondo", txt)

    def test_as_dict_roundtrip(self):
        payload = json.loads(json.dumps(self.tr.as_dict()))
        self.assertEqual(payload["language"], "it")
        self.assertEqual(len(payload["segments"]), 2)
        self.assertEqual(payload["text"], "Ciao mondo Seconda riga")


if __name__ == "__main__":
    unittest.main()
