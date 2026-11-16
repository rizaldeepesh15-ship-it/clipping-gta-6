"""clipper.cloud: local-file import, TikTok captions and the posting package."""
import json
import shutil
import subprocess
import tempfile
import unittest
import zipfile
from pathlib import Path

from clipper import cloud

FFMPEG = all(shutil.which(t) for t in ("ffmpeg", "ffprobe"))


class TikTokCaption(unittest.TestCase):
    def test_title_credit_and_tags_without_shorts(self):
        desc = "Kai was NOT ready\n\nClip from Kai Cenat: https://youtu.be/x\n\n#gta6 #gtavi #shorts"
        cap = cloud.tiktok_caption("Kai was NOT ready for GTA 6", desc)
        self.assertTrue(cap.startswith("Kai was NOT ready for GTA 6\n\n"))
        self.assertIn("Clip from Kai Cenat: https://youtu.be/x", cap)
        self.assertTrue(cap.endswith("#gta6 #gtavi #fyp #gaming"))
        self.assertNotIn("#shorts", cap)

    def test_no_duplicate_tags_and_length_cap(self):
        cap = cloud.tiktok_caption("T", "x" * 3000 + " #GTA6", ["#gta6", "#fyp"])
        self.assertLessEqual(len(cap), cloud.TIKTOK_MAX)
        cap = cloud.tiktok_caption("T", "body #gta6", ["#GTA6", "#fyp"])
        self.assertEqual(cap.lower().count("#gta6"), 1)
        self.assertEqual(cap.count("#fyp"), 1)

    def test_seconds(self):
        self.assertEqual(cloud.seconds("1:02:03"), 3723)
        self.assertEqual(cloud.seconds("62:03"), 3723)
        self.assertEqual(cloud.seconds("90"), 90)


class Package(unittest.TestCase):
    def test_posting_notes_and_zip(self):
        with tempfile.TemporaryDirectory() as d:
            run = Path(d) / "2026-11-16"
            for n in (1, 2, 10):
                vf = run / f"video {n}"
                vf.mkdir(parents=True)
                (vf / "hook a.mp4").write_bytes(b"\0" * 100)
                (vf / "titles and description.md").write_text("# t\n")
                (vf / "upload.json").write_text(json.dumps([{
                    "file": str(vf / "hook a.mp4"), "hook": "Hook a", "title": f"Title {n} GTA 6",
                    "description": f"Desc {n}\n\nClip from X: y\n\n#gta6 #shorts", "duration": 31.4,
                    "predicted": 1.5}]))
            posting, archive, mp4s = cloud.package(run)
            self.assertEqual([m.parent.name for m in mp4s], ["video 1", "video 2", "video 10"])
            text = posting.read_text()
            self.assertIn("## video 10 / hook a.mp4", text)
            self.assertIn("Title 2 GTA 6", text)
            self.assertIn("#gta6 #fyp #gaming", text)
            names = zipfile.ZipFile(archive).namelist()
            self.assertIn("video 1/hook a.mp4", names)
            self.assertIn("POSTING.md", names)
            self.assertNotIn(archive.name, names)

    def test_empty_folder_fails(self):
        with tempfile.TemporaryDirectory() as d, self.assertRaises(SystemExit):
            cloud.package(d)


@unittest.skipUnless(FFMPEG, "needs ffmpeg and ffprobe")
class Import(unittest.TestCase):
    def make_video(self, path, seconds=6, audio=True):
        cmd = ["ffmpeg", "-loglevel", "error", "-y", "-f", "lavfi", "-i", f"testsrc=size=320x240:rate=25:d={seconds}"]
        if audio:
            cmd += ["-f", "lavfi", "-i", f"sine=frequency=440:d={seconds}"]
        subprocess.run(cmd + ["-c:v", "mpeg4", "-shortest", str(path)], check=True)

    def test_import_cut_and_never_replace(self):
        with tempfile.TemporaryDirectory() as d:
            src = Path(d) / "stream.mov"
            self.make_video(src)
            jobs = Path(d) / "jobs"
            job = cloud.import_video(src, "Kai Cenat", "Kai plays GTA 6", "https://youtu.be/abc", "0:01", "0:04",
                                     "t1", jobs)
            meta = json.loads((job / "job.json").read_text())
            self.assertEqual(meta["channel"], "Kai Cenat")
            self.assertEqual(meta["offset"], 1.0)
            self.assertAlmostEqual(meta["duration"], 3, delta=1)
            info = json.loads((job / "source.info.json").read_text())
            self.assertEqual(info["title"], "Kai plays GTA 6")
            kinds, _ = cloud.probe(job / "source.mp4")
            self.assertEqual(kinds, {"video", "audio"})
            with self.assertRaises(SystemExit):
                cloud.import_video(src, "Kai Cenat", job_id="t1", jobs=jobs)

    def test_rejects_silent_video(self):
        with tempfile.TemporaryDirectory() as d:
            src = Path(d) / "silent.mp4"
            self.make_video(src, audio=False)
            with self.assertRaises(SystemExit):
                cloud.import_video(src, "X", jobs=Path(d) / "jobs")
            self.assertFalse((Path(d) / "jobs").exists() and any((Path(d) / "jobs").iterdir()))


if __name__ == "__main__":
    unittest.main()
