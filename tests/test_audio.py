"""Test per classificazione media e utilità audio (senza binari esterni)."""

import unittest
from pathlib import Path

from stt_tts_ita.audio import (
    AUDIO_EXTENSIONS,
    MEDIA_EXTENSIONS,
    VIDEO_EXTENSIONS,
    is_video,
)
from stt_tts_ita.transcribe import Segment, Transcript


class TestMediaDetection(unittest.TestCase):
    def test_audio_is_not_video(self):
        for ext in (".m4a", ".wav", ".mp3"):
            self.assertIn(ext, AUDIO_EXTENSIONS)
            self.assertFalse(is_video(Path(f"x{ext}")))

    def test_video_detected(self):
        for ext in (".mp4", ".mkv", ".webm", ".mov", ".avi"):
            self.assertIn(ext, VIDEO_EXTENSIONS)
            self.assertTrue(is_video(Path(f"x{ext}")))

    def test_media_is_union(self):
        self.assertEqual(MEDIA_EXTENSIONS, AUDIO_EXTENSIONS | VIDEO_EXTENSIONS)

    def test_case_insensitive(self):
        self.assertTrue(is_video(Path("CLIP.MP4")))


class TestTranscript(unittest.TestCase):
    def test_text_join(self):
        tr = Transcript(segments=[Segment(0, 1, " uno "), Segment(1, 2, "due")])
        self.assertEqual(tr.text, "uno due")


if __name__ == "__main__":
    unittest.main()
