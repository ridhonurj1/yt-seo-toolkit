"""Tests untuk ytseo.sync — integrasi clipper v3 -> YouTube."""
import json
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).parent.parent))
from ytseo.sync import plan_sync, build_hook_text, load_clip, V3_DB


def _make_v3_db(path: Path, clip_row: dict) -> None:
    c = sqlite3.connect(path)
    c.execute(
        "CREATE TABLE clips (id TEXT PRIMARY KEY, project_id TEXT, idx INTEGER, "
        "start_sec REAL, end_sec REAL, duration REAL, category TEXT, score REAL, "
        "hook TEXT, reason TEXT, transcript_json TEXT, titles_json TEXT, title TEXT, "
        "description TEXT, hashtags_json TEXT, style_json TEXT, media_json TEXT, "
        "aspect TEXT, platform TEXT, status TEXT, video_path TEXT, thumb_path TEXT, "
        "srt_path TEXT, translations_json TEXT, active_lang TEXT, error TEXT, "
        "created_at TEXT, brand_json TEXT)"
    )
    cols = [r[1] for r in c.execute("pragma table_info(clips)")]
    row = {k: None for k in cols}
    row.update(clip_row)
    c.execute(
        f"INSERT INTO clips ({','.join(cols)}) VALUES ({','.join('?' for _ in cols)})",
        [row[k] for k in cols],
    )
    c.commit()
    c.close()


class TestSync(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = Path(self.tmp.name) / "clipper.db"
        _make_v3_db(self.db, {
            "id": "test-clip-1",
            "project_id": "p1",
            "idx": 1,
            "duration": 75.0,
            "hook": "Band ini nolak bawain lagu paling viral mereka saat manggung",
            "transcript_json": json.dumps([
                {"text": "katanya bosan", "start": 0.0},
                {"text": "padahal fans minta", "start": 5.0},
            ]),
            "title": "Nolak Bawain Lagu Viral Sendiri Pas Manggung?!",
            "status": "completed",
            "video_path": "data/media/projects/p1/clip-01.mp4",
        })

    def tearDown(self):
        self.tmp.cleanup()

    def test_load_clip(self):
        with patch("ytseo.sync.V3_DB", self.db):
            clip = load_clip("test-clip-1")
        self.assertEqual(clip["title"], "Nolak Bawain Lagu Viral Sendiri Pas Manggung?!")

    def test_plan_title_passthrough(self):
        with patch("ytseo.sync.V3_DB", self.db):
            clip = load_clip("test-clip-1")
        plan = plan_sync(clip)
        self.assertEqual(plan["final_title"], clip["title"])
        self.assertEqual(plan["title_issues"], [])

    def test_plan_has_brand_tags(self):
        with patch("ytseo.sync.V3_DB", self.db):
            clip = load_clip("test-clip-1")
        plan = plan_sync(clip)
        for t in ("rizz snipbit", "podcast indonesia"):
            self.assertIn(t, plan["final_tags"])
        self.assertIn("nolak bawain", plan["final_tags"])

    def test_plan_chapters_for_60s_plus(self):
        with patch("ytseo.sync.V3_DB", self.db):
            clip = load_clip("test-clip-1")
        plan = plan_sync(clip)
        self.assertIsNotNone(plan["chapters"])
        self.assertTrue(plan["chapters"].startswith("00:00"))

    def test_plan_desc_starts_with_hook(self):
        with patch("ytseo.sync.V3_DB", self.db):
            clip = load_clip("test-clip-1")
        plan = plan_sync(clip)
        self.assertTrue(plan["final_description"].startswith("Band ini nolak"))

    def test_hook_text_two_lines_max14(self):
        t = build_hook_text("Nolak Bawain Lagu Viral Sendiri Pas Manggung?! #tag")
        lines = t.splitlines()
        self.assertLessEqual(len(lines), 2)
        for l in lines:
            self.assertLessEqual(len(l), 14)


if __name__ == "__main__":
    unittest.main()
