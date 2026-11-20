"""On-screen credit (`credit_tag`): what text it shows and where it's drawn."""
import tempfile
import unittest
from pathlib import Path

from PIL import Image

from clipper import captions, render


def alpha_rows(png):
    """Rows (y) that have any visible pixel in a full-frame overlay."""
    a = Image.open(png).getchannel("A")
    w, h = a.size
    px = a.load()
    return {y for y in range(h) if any(px[x, y] for x in range(0, w, 4))}


class CreditText(unittest.TestCase):
    creds = [("IShowSpeed", "https://youtu.be/x"), ("Kai Cenat", "https://youtu.be/y"), ("IShowSpeed", "z")]

    def test_off_unless_asked(self):
        self.assertIsNone(render.credit_text({}, self.creds))
        self.assertIsNone(render.credit_text({"credit_tag": False}, self.creds, {"credit_tag": True}))

    def test_true_names_every_streamer_once(self):
        self.assertEqual(render.credit_text({"credit_tag": True}, self.creds), "@IShowSpeed · @KaiCenat")

    def test_string_is_used_as_written(self):
        self.assertEqual(render.credit_text({"credit_tag": " @ishowspeed "}, self.creds), "@ishowspeed")

    def test_profile_default_applies_when_pick_is_silent(self):
        self.assertEqual(render.credit_text({}, self.creds[:1], {"credit_tag": True}), "@IShowSpeed")


class CreditDrawing(unittest.TestCase):
    def test_tag_drawn_at_credit_y_even_without_a_hook(self):
        with tempfile.TemporaryDirectory() as d:
            for layout in ("fit", "split"):
                png = Path(d) / f"{layout}.png"
                captions.render_hook("", png, "bold", layout, "@IShowSpeed")
                rows = alpha_rows(png)
                y = captions.LAYOUTS[layout]["credit_y"]
                self.assertIn(y, rows)
                self.assertTrue(all(abs(r - y) < 45 for r in rows), f"{layout}: drawn away from the tag line")

    def test_no_credit_leaves_overlay_unchanged(self):
        with tempfile.TemporaryDirectory() as d:
            plain, none = Path(d) / "a.png", Path(d) / "b.png"
            captions.render_hook("Speed was NOT ready for *GTA 6*", plain, "bold", "fit")
            captions.render_hook("Speed was NOT ready for *GTA 6*", none, "bold", "fit", None)
            self.assertEqual(Image.open(plain).tobytes(), Image.open(none).tobytes())
            self.assertFalse(alpha_rows(plain) & set(range(1280, 1340)))

    def test_tag_clears_hook_and_captions(self):
        for layout, spot in captions.LAYOUTS.items():
            self.assertGreater(spot["credit_y"] - 30, spot["hook_y"] + 180, layout)
            self.assertGreater(abs(spot["credit_y"] - spot["caption_y"]), 85, layout)

    def test_long_credit_shrinks_to_fit(self):
        with tempfile.TemporaryDirectory() as d:
            png = Path(d) / "long.png"
            captions.render_hook("", png, "bold", "fit", " · ".join(["@AVeryLongStreamerName"] * 4))
            a = Image.open(png).getchannel("A")
            cols = [x for x in range(a.width) if a.getpixel((x, captions.LAYOUTS["fit"]["credit_y"]))]
            self.assertGreater(min(cols), 60)
            self.assertLess(max(cols), a.width - 60)


if __name__ == "__main__":
    unittest.main()
