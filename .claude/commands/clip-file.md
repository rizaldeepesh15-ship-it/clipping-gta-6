---
description: Clip a GTA 6 video file you send (no download) in a cloud session, and hand every finished MP4 back to you
argument-hint: [path to video | Google Drive link] [streamer name] [original stream link]
---

Clip a video file the user already has, in a Claude cloud session (or anywhere the stream can't be downloaded). Run everything from the clipping-gta-6 project root. In a cloud session the project's Python is `.venv/bin/python` (`uv sync` made it): wherever `.claude/commands/clip.md` says `python3`, use `.venv/bin/python`. The user may be on a phone or tablet: keep questions to multiple choice where possible, and never ask them to type commands.

Input: $ARGUMENTS

1. **Find the video.**
   - A path in the arguments: use it.
   - Otherwise run `.venv/bin/python -m clipper.cloud find` (lists video files on this machine, newest first). A file the user just attached is usually the newest one.
   - A share link (Google Drive and the like): this cloud environment only reaches allowed hosts. Try `yt-dlp -o "$HOME/uploads/%(title)s.%(ext)s" <link>` (Drive links: `curl -L` the `drive.usercontent.google.com/download?id=<id>&export=download&confirm=t` form). If the host is refused, ask the user to allow that exact host (never unrestricted network access).
   - Nothing found: tell the user how to send one (attach it in this chat, or share a link) and stop.
2. **Who and what.** Get the streamer's name (for the credit), a short title of what the video is ("Kai Cenat plays GTA 6 for the first time"), and the link to the original stream or VOD (for the credit line). Take them from the arguments, the file name, or ask. If there is no link, carry on and say the descriptions credit the name only. For a source over about 2 hours, ask which part to clip (or suggest the first 90 minutes): analysis on this CPU-only machine runs at roughly real-time ÷ 3.
3. **Setup questions.** Ask the questions from `.claude/commands/clip.md` step 1 (voiceover, how many videos, hooks per video, save as defaults). In a cloud session, recommend **No voiceover**: Fish Audio's host isn't allowed here, so the only voice is the robotic espeak-ng one.
4. **Import.** `.venv/bin/python -m clipper.cloud import "<file>" --channel "<name>" --title "<title>" --url "<link>" [--start H:MM:SS --end H:MM:SS]`. It prints the job name. It never replaces an existing job.
5. **Analyze.** `.venv/bin/python -m clipper analyze <job>` (Parakeet transcription, loudness, hype words and laughter scoring). Run it in the background for long sources and tell the user roughly how long it will take. It writes `jobs/<job>/candidates.md`, `transcript.json` and `review/` contact sheets.
6. **Review, pick, check, simulate, render.** Follow `.claude/commands/clip.md` steps 4, 6, 7 and 8 exactly (read `research/viral-gta-shorts.md` first; present the picks table and wait for approval; layout via `clipper frame`; picks.json; `clipper check` and `clipper simulate`; `clipper render <job> --picks jobs/<job>/picks.json`). Skip step 5 unless the user chose voiceovers and has a Fish key saved. Every clip is a 1080x1920 MP4 with word-by-word animated captions, one MP4 per hook, plus `titles and description.md`.
7. **Look before delivering.** Extract a frame or two from each MP4 with ffmpeg and look at them (captions readable, facecam not covered, nothing cut off).
8. **Deliver to the user's device.** The cloud machine is deleted when the session goes idle, and `exports/` is never committed, so the user must save the files now.
   - `.venv/bin/python -m clipper.cloud package exports/<profile>/<date>` writes `POSTING.md` (per MP4: YouTube Shorts title and description, TikTok caption) and a `<date>-clips.zip` of every MP4 and note.
   - Send every MP4 with SendUserFile (display `attach`) as soon as it's checked, then `POSTING.md`, then the zip. Before the zip, note it holds only that date's clips.
   - Tell the user: tap each card → Share → **Save Video** (Photos) or **Save to Files**; the zip goes to Files.
9. **Report.** A table per video (hook files, title, length, source timestamp). Remind the user to only post clips they have the rights or the creator's permission to use, and to A/B test the hook variants.
