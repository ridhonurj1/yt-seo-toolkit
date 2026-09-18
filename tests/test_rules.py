"""Tests untuk modul rules, chapters, endscreen, thumbnail (offline, tanpa API)."""

import unittest
from pathlib import Path

from ytseo.rules import (
    audit_title, audit_tags, build_description, description_snippet,
    extract_hashtags_from_text, normalize_tags, suggest_tags_from_title_and_desc,
    tags_total_length, TITLE_SAFE_LIMIT,
)
from ytseo.chapters import parse_chapters, build_chapters_block, validate_block
from ytseo.endscreen import plan_end_screen, plan_cards, audit_end_screen_json


class TestTitle(unittest.TestCase):
    def test_ok_title(self):
        a = audit_title("3 Cara Akses Cepat Fitur Baru di 2026")
        self.assertTrue(a.ok, a.issues)

    def test_too_long_flagged(self):
        t = "X" * (TITLE_SAFE_LIMIT + 10)
        a = audit_title(t)
        self.assertFalse(a.ok)
        self.assertTrue(any("zona aman" in i for i in a.issues))

    def test_hard_limit_suggestion(self):
        t = "Y" * 120
        a = audit_title(t)
        self.assertTrue(any(str(120) in i for i in a.issues))
        self.assertTrue(a.suggestions)

    def test_all_caps_flagged(self):
        a = audit_title("INI ADALAH JUDUL VIDEO YANG SANGAT PANJANG SEKALI MEMANG")
        self.assertTrue(any("ALL-CAPS" in i for i in a.issues))

    def test_empty_title(self):
        a = audit_title("")
        self.assertFalse(a.ok)
        self.assertTrue(a.issues)


class TestDescription(unittest.TestCase):
    def test_snippet_is_first_150(self):
        hook = "Kunci utama performa video ada di 3 teknik ini"
        desc = build_description(hook, ["body"], hashtags=["satu", "dua"])
        s = description_snippet(desc)
        self.assertTrue(s.startswith(hook))
        self.assertLessEqual(len(s), 150)

    def test_chapters_after_hook(self):
        desc = build_description("HOOK", ["body"], chapters="00:00 Intro\n00:15 Isi")
        self.assertTrue(desc.startswith("HOOK"))
        self.assertIn("00:00 Intro", desc)
        # hook dulu, chapters setelahnya
        self.assertLess(desc.index("HOOK"), desc.index("00:00"))

    def test_hashtags_appended(self):
        desc = build_description("H", [], hashtags=["abc", "def"])
        self.assertIn("#abc #def", desc)

    def test_over_15_hashtags_extract_only_15(self):
        text = " ".join(f"#tag{i}" for i in range(20))
        self.assertEqual(len(extract_hashtags_from_text(text)), 15)


class TestTags(unittest.TestCase):
    def test_normalize_dedupe_and_lowercase(self):
        out = normalize_tags(["Alpha", "alpha", " Beta ", ""])
        self.assertEqual(out, ["alpha", "beta"])

    def test_total_length_limit(self):
        raw = [f"tag-yang-sangat-panjang-sekali-{i}" for i in range(50)]
        out = normalize_tags(raw)
        self.assertLessEqual(tags_total_length(out), 500)
        self.assertLessEqual(len(out), 30)

    def test_suggest_from_title(self):
        tags = suggest_tags_from_title_and_desc(
            "Cara Menanam Cabai Hidroponik untuk Pemula", "panen cabai dalam 3 bulan"
        )
        self.assertIn("menanam cabai", tags)
        self.assertTrue(any("hidroponik" in t for t in tags))

    def test_audit_reports_trim(self):
        raw = [f"t{i}" for i in range(40)]
        issues, cleaned = audit_tags(raw)
        self.assertTrue(any("dipangkas" in i for i in issues))
        self.assertEqual(len(cleaned), 30)


class TestChapters(unittest.TestCase):
    def test_valid_block(self):
        block = "00:00 Intro\n00:20 Materi\n01:30 Penutup"
        self.assertEqual(validate_block(block), [])

    def test_first_must_be_zero(self):
        errors = validate_block("00:10 A\n00:30 B\n01:00 C")
        self.assertTrue(any("00:00" in e for e in errors))

    def test_too_short_gap(self):
        errors = validate_block("00:00 A\n00:05 B\n01:00 C")
        self.assertTrue(any("pendek" in e for e in errors))

    def test_fewer_than_three(self):
        _, errors = parse_chapters("00:00 A\n00:30 B")
        self.assertTrue(any("minimal" in e for e in errors))

    def test_build_raises_on_short(self):
        with self.assertRaises(ValueError):
            build_chapters_block([(0, "A"), (5, "B"), (60, "C")])

    def test_build_normal(self):
        block = build_chapters_block([(0, "Intro"), (45, "Isi"), (130, "End")])
        self.assertEqual(block.splitlines()[0], "00:00 Intro")
        self.assertEqual(block.splitlines()[2], "02:10 End")

    def test_unparseable_line(self):
        _, errors = parse_chapters("intro aja tanpa timestamp")
        self.assertTrue(any("tidak dikenali" in e for e in errors))


class TestEndScreen(unittest.TestCase):
    def test_short_video_no_endscreen(self):
        plan = plan_end_screen(30)
        self.assertEqual(plan.duration_sec, 0)
        self.assertTrue(any("< 35s" in n for n in plan.notes))

    def test_normal_video_has_elements(self):
        plan = plan_end_screen(600, best_video_id="abc123", playlist_id="PL-1")
        kinds = [e.kind for e in plan.elements]
        self.assertIn("video", kinds)
        self.assertIn("subscribe", kinds)
        self.assertIn("playlist", kinds)
        self.assertTrue(5 <= plan.duration_sec <= 20)

    def test_json_serializable(self):
        import json
        plan = plan_end_screen(600, best_video_id="x")
        d = audit_end_screen_json(plan)
        json.dumps(d)  # tidak boleh raise
        self.assertIn("studio_steps", d)

    def test_cards_spread(self):
        pts = plan_cards(600, [])
        self.assertTrue(pts)
        self.assertTrue(all(30 <= p <= 540 + 10 for p in pts))

    def test_cards_short_video_empty(self):
        self.assertEqual(plan_cards(45, []), [])


class TestThumbnail(unittest.TestCase):
    def _make_image_bytes(self, color, size=(1280, 720), fmt="PNG"):
        from PIL import Image
        import io
        img = Image.new("RGB", size, color)
        buf = io.BytesIO()
        img.save(buf, format=fmt)
        return buf.getvalue()

    def test_flat_dark_image_flagged(self):
        from ytseo.thumbnail import audit_thumbnail
        a = audit_thumbnail(self._make_image_bytes((10, 10, 10)))
        self.assertTrue(any("gelap" in i for i in a.issues))
        self.assertTrue(any("kontras" in i for i in a.issues))

    def test_good_image_scores_better(self):
        from ytseo.thumbnail import audit_thumbnail
        # gambar dengan kontras bawaan: pola kotak hitam-putih
        from PIL import Image
        import io
        img = Image.new("RGB", (1280, 720), (255, 255, 255))
        for x in range(0, 1280, 80):
            for y in range(0, 720, 80):
                if (x // 80 + y // 80) % 2 == 0:
                    img.paste((0, 0, 0), (x, y, x + 80, y + 80))
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        a = audit_thumbnail(buf.getvalue())
        b = audit_thumbnail(self._make_image_bytes((10, 10, 10)))
        self.assertGreater(a.score, b.score)

    def test_wrong_aspect_flagged(self):
        from ytseo.thumbnail import audit_thumbnail
        a = audit_thumbnail(self._make_image_bytes((128, 128, 128), size=(640, 720)))
        self.assertTrue(any("rasio" in i for i in a.issues))

    def test_upload_constraints(self):
        from ytseo.thumbnail import check_upload_constraints
        errs = check_upload_constraints(b"x" * (3 * 1024 * 1024), "image/jpeg")
        self.assertTrue(any("2MB" in e for e in errs))
        errs2 = check_upload_constraints(b"x" * 100, "image/tiff")
        self.assertTrue(any("tidak didukung" in e for e in errs2))


if __name__ == "__main__":
    unittest.main()
