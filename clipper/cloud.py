"""Clip a video file you already have (no download), then package the results for posting.

Made for cloud sessions, where streams can't be downloaded and finished clips must be handed over before the
machine goes away:

  python -m clipper.cloud find                                   # video files sent to this machine
  python -m clipper.cloud import <file> --channel "Kai Cenat" --title "Kai plays GTA 6" --url <original link>
                                       [--start H:MM:SS --end H:MM:SS] [--id name]
  python -m clipper analyze <job>                                # then /clip steps 4-8 as usual
  python -m clipper.cloud package exports/gta6/<date>            # POSTING.md (Shorts + TikTok) and one .zip

`import` makes the same job folder `clipper fetch` makes (source.mp4, job.json, source.info.json), so analyze,
check, simulate and render work on it unchanged. It never replaces an existing job.
"""
import argparse
import json
import re
import shutil
import subprocess
import sys
import time
import zipfile
from datetime import datetime
from pathlib import Path

from . import config

VIDEO_EXT = {".mp4", ".mov", ".m4v", ".mkv", ".webm", ".ts", ".flv", ".avi"}
TIKTOK_MAX = 2200  # TikTok's caption limit has grown over time; 2200 fits everywhere
SEARCH_DIRS = ["~/Downloads", "~/uploads", "/tmp", "/mnt", "/home/user", "~"]


def slug(text):
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")[:40] or "video"


def seconds(t):
    """'1:02:03', '62:03' or '3723' -> 3723.0"""
    total = 0.0
    for part in str(t).split(":"):
        total = total * 60 + float(part)
    return total


def probe(path):
    out = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "stream=codec_type:format=duration",
                          "-of", "json", str(path)], capture_output=True, text=True)
    if out.returncode:
        raise SystemExit(f"not a readable video: {path}\n{out.stderr.strip()}")
    data = json.loads(out.stdout or "{}")
    kinds = {s.get("codec_type") for s in data.get("streams", [])}
    return kinds, float((data.get("format") or {}).get("duration") or 0)


def import_video(path, channel, title=None, url="", start=None, end=None, job_id=None, jobs=None):
    """Copy (or cut) a local video into jobs/<id>/ as a ready-to-analyze job. Returns the job folder."""
    path = Path(path).expanduser().resolve()
    if not path.is_file():
        raise SystemExit(f"no such file: {path}")
    kinds, dur = probe(path)
    if "video" not in kinds or "audio" not in kinds:
        raise SystemExit(f"{path.name} needs both video and audio (found: {', '.join(sorted(k for k in kinds if k)) or 'nothing'})")
    jobs = Path(jobs) if jobs else config.JOBS
    title = title or path.stem
    job_id = job_id or f"local-{slug(channel)}-{datetime.now():%Y%m%d-%H%M%S}"
    job = jobs / job_id
    if job.exists():
        raise SystemExit(f"job {job_id} already exists; pick another --id (existing jobs are never replaced)")
    s = seconds(start) if start else 0.0
    e = seconds(end) if end else None
    if e is not None and e <= s:
        raise SystemExit("--end must be after --start")
    cut = (["-ss", f"{s:.3f}"] if s else []) + (["-to", f"{e:.3f}"] if e is not None else [])
    job.mkdir(parents=True)
    src = job / "source.mp4"
    try:
        # stream copy keeps full quality and takes seconds; codecs MP4 can't hold are re-encoded instead
        ok = subprocess.run(["ffmpeg", "-y", "-loglevel", "error", *cut, "-i", str(path), "-map", "0:v:0", "-map",
                             "0:a:0", "-c", "copy", "-movflags", "+faststart", str(src)]).returncode == 0
        if not ok:
            subprocess.run(["ffmpeg", "-y", "-loglevel", "error", *cut, "-i", str(path), "-map", "0:v:0", "-map",
                            "0:a:0", "-c:v", "libx264", "-preset", "veryfast", "-crf", "18", "-pix_fmt", "yuv420p",
                            "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart", str(src)], check=True)
        _, dur = probe(src)
    except BaseException:
        shutil.rmtree(job, ignore_errors=True)
        raise
    meta = {"id": job_id, "url": url or "", "title": title, "channel": channel, "duration": round(dur),
            "offset": s, "local_file": path.name, "imported_at": time.time(), "profile": config.PROFILE}
    (job / "job.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")
    (job / "source.info.json").write_text(json.dumps({"title": title, "channel": channel, "uploader": channel,
                                                      "duration": round(dur), "is_live": False}, indent=2),
                                          encoding="utf-8")
    return job


def find_videos(dirs=None, min_mb=1.0):
    """Video files outside the project's jobs/exports, newest first: where an upload to this machine landed."""
    skip = {config.JOBS.resolve(), (config.ROOT / "exports").resolve(), (config.ROOT / ".venv").resolve()}
    seen, found = set(), []
    for d in dirs or SEARCH_DIRS:
        base = Path(d).expanduser()
        if not base.is_dir():
            continue
        for depth in range(4):
            for f in base.glob("/".join(["*"] * (depth + 1))):
                try:
                    if (f.suffix.lower() not in VIDEO_EXT or not f.is_file() or f in seen
                            or any(p in skip for p in f.resolve().parents)
                            or any(part.startswith(".") for part in f.relative_to(base).parts)):
                        continue
                    size = f.stat().st_size / 1e6
                except OSError:
                    continue
                if size >= min_mb:
                    seen.add(f)
                    found.append((f.stat().st_mtime, size, f))
    return [(f, size) for _, size, f in sorted(found, reverse=True)]


def tiktok_caption(title, description, hashtags=None):
    """TikTok has no separate title: the hook line, the credit, then hashtags (#shorts swapped for #fyp)."""
    body = description or ""
    tags = re.findall(r"#\w+", body) + list(hashtags or [])
    body = re.sub(r"(?:\s*#\w+)+\s*$", "", body).strip()  # trailing hashtag line; re-added below
    if body.startswith(title):
        body = body[len(title):].strip()
    out, seen = [], set()
    for t in tags + ["#fyp", "#gaming"]:
        low = t.lower()
        if low in ("#shorts", "#short", "#ytshorts") or low in seen:
            continue
        seen.add(low)
        out.append(t)
    caption = "\n\n".join(p for p in (title, body, " ".join(out)) if p)
    return caption[:TIKTOK_MAX]


def video_folders(folder):
    folder = Path(folder)
    if (folder / "upload.json").exists():
        return [folder]
    num = lambda p: int(re.sub(r"\D", "", p.name) or 0)
    return sorted((p for p in folder.iterdir() if p.is_dir() and (p / "upload.json").exists()), key=num)


def tidy_credit(text):
    """'Clip from xQc: ' (a source imported without a link) -> 'Clip from xQc'."""
    return re.sub(r"(?m)^(Clips? from [^\n]*?):[ \t]*$", r"\1", text or "")


def posting_markdown(folder):
    lines = [f"# Ready to post: {Path(folder).name}", "",
             "One section per MP4. YouTube Shorts: paste the title and description. "
             "TikTok: paste the caption (TikTok has no separate title). "
             "Post each hook variant as its own upload to A/B test, and only post clips you have the rights "
             "or the creator's permission to use.", ""]
    for vf in video_folders(folder):
        for item in json.loads((vf / "upload.json").read_text(encoding="utf-8")):
            name = Path(item["file"]).name
            title = (item.get("title") or "")[:100]
            desc = tidy_credit(item.get("description") or title)
            lines += [f"## {vf.name} / {name}", "",
                      f"Hook on screen: {item.get('hook') or '(none)'} · {item.get('duration', 0):.0f}s"
                      + (f" · predicted {item['predicted']}x" if item.get("predicted") else ""), "",
                      "**YouTube Shorts title**", "", "```", title, "```", "",
                      "**YouTube Shorts description**", "", "```", desc, "```", "",
                      "**TikTok caption**", "", "```", tiktok_caption(title, desc, item.get("hashtags")), "```", ""]
    return "\n".join(lines)


def package(folder, make_zip=True):
    """Write POSTING.md into the export folder and zip its MP4s + notes. Returns (posting, zip or None, mp4s)."""
    folder = Path(folder).expanduser().resolve()
    if not folder.is_dir():
        raise SystemExit(f"no such folder: {folder}")
    if not video_folders(folder):
        raise SystemExit(f"no rendered videos (upload.json) in {folder}")
    posting = folder / "POSTING.md"
    posting.write_text(posting_markdown(folder), encoding="utf-8")
    mp4s = [p for vf in video_folders(folder) for p in sorted(vf.glob("*.mp4"))]
    archive = None
    if make_zip:
        archive = folder / f"{folder.name}-clips.zip"
        with zipfile.ZipFile(archive, "w") as z:
            for p in sorted(folder.rglob("*")):
                if p.is_file() and p != archive and p.suffix.lower() in (".mp4", ".md"):
                    # MP4s are already compressed: storing them is as small and far faster
                    z.write(p, p.relative_to(folder), zipfile.ZIP_STORED if p.suffix == ".mp4" else zipfile.ZIP_DEFLATED)
    return posting, archive, mp4s


def main(argv=None):
    ap = argparse.ArgumentParser(prog="clipper.cloud", description=__doc__.split("\n\n")[0])
    ap.add_argument("--profile", help="niche profile (default gta6)")
    sub = ap.add_subparsers(dest="cmd", required=True)
    f = sub.add_parser("find", help="list video files sent to this machine, newest first")
    f.add_argument("dirs", nargs="*")
    i = sub.add_parser("import", help="make a job from a local video file")
    i.add_argument("file")
    i.add_argument("--channel", required=True, help="the streamer/creator, credited in every description")
    i.add_argument("--title", help="what the video is (helps the analysis guess the clip type)")
    i.add_argument("--url", default="", help="link to the original stream/video, for the credit line")
    i.add_argument("--start", help="only this part: start H:MM:SS")
    i.add_argument("--end", help="only this part: end H:MM:SS")
    i.add_argument("--id", help="job name (default local-<channel>-<time>)")
    p = sub.add_parser("package", help="POSTING.md (Shorts + TikTok text) and a zip for an export folder")
    p.add_argument("folder")
    p.add_argument("--no-zip", action="store_true")
    args = ap.parse_args(argv)
    config.load(profile=args.profile)
    if args.cmd == "find":
        vids = find_videos(args.dirs or None)
        if not vids:
            print("no video files found")
        for path, size in vids:
            print(f"{size:9.1f} MB  {path}")
    elif args.cmd == "import":
        if not args.url:
            print("note: no --url given; descriptions will credit the channel without a link to the original",
                  file=sys.stderr)
        job = import_video(args.file, args.channel, args.title, args.url, args.start, args.end, args.id)
        meta = json.loads((job / "job.json").read_text(encoding="utf-8"))
        print(f"job ready: {job.name} ({meta['duration'] / 60:.1f} min)\nnext: python -m clipper analyze {job.name}")
    elif args.cmd == "package":
        posting, archive, mp4s = package(args.folder, not args.no_zip)
        print(f"{len(mp4s)} MP4s")
        for m in mp4s:
            print(f"  {m}")
        print(f"posting notes: {posting}")
        if archive:
            print(f"zip: {archive} ({archive.stat().st_size / 1e6:.1f} MB)")


if __name__ == "__main__":
    main()
