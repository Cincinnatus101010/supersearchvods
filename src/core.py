"""Transcript fetch, Whisper fallback, and sliding-window search."""

from __future__ import annotations

import concurrent.futures
import logging
import os
import re
import subprocess
import tempfile
import threading
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from supersearch.ytdlp import subprocess_env, ytdlp_argv, ytdlp_extra_argv

LOG = logging.getLogger(__name__)

_CPU = os.cpu_count() or 4
_WHISPER_MODEL = os.environ.get("SUPERSEARCH_WHISPER_MODEL", "base")
_WHISPER_WORKERS = int(os.environ.get("SUPERSEARCH_WHISPER_WORKERS", str(max(1, _CPU // 2))))
_WHISPER_DL_WORKERS = int(os.environ.get("SUPERSEARCH_WHISPER_DL_WORKERS", str(min(_CPU, 16))))
_WHISPER_CHUNK_SEC = float(os.environ.get("SUPERSEARCH_WHISPER_CHUNK_SEC", "600"))

_AUDIO_SUFFIXES = frozenset({".mp3", ".m4a", ".opus", ".webm", ".wav"})
_CAPTION_SUFFIXES = frozenset({"vtt", "webvtt", "srt"})
_TS_RANGE = re.compile(r"(\d+:\d+[\d:.,]+)\s+-->\s+(\d+:\d+[\d:.,]+)")
_VTT_TAG = re.compile(r"<[^>]+>")
_YT_BA = "(ba[format_note*=original]/ba[language^=en]/ba)"
_YTDLP_AUDIO = f"{_YT_BA}/bestaudio/worstvideo+{_YT_BA}/worst"

_tl = threading.local()


@dataclass
class TranscriptEntry:
    start: float
    end: float
    text: str


@dataclass
class SearchResult:
    start: float
    end: float
    text: str
    score: float
    context: str = field(default="")


def _ts_to_sec(ts: str) -> float:
    ts = ts.replace(",", ".")
    parts = ts.split(":")
    try:
        if len(parts) == 3:
            return int(parts[0]) * 3600 + int(parts[1]) * 60 + float(parts[2])
        if len(parts) == 2:
            return int(parts[0]) * 60 + float(parts[1])
        return float(ts)
    except ValueError:
        return 0.0


def _parse_captions(content: str, fmt: str) -> list[TranscriptEntry]:
    is_srt = fmt == "srt"
    entries: list[TranscriptEntry] = []
    for block in re.split(r"\n{2,}", content.strip()):
        lines = block.strip().splitlines()
        ts_match = None
        text_parts: list[str] = []
        for line in lines:
            match = _TS_RANGE.search(line)
            if match:
                ts_match = match
                text_parts = []
                continue
            if not ts_match:
                continue
            clean = _VTT_TAG.sub("", line).strip()
            if not clean:
                continue
            if is_srt and re.fullmatch(r"\d+", clean):
                continue
            if not is_srt and clean.isdigit():
                continue
            text_parts.append(clean)
        if ts_match and text_parts:
            entries.append(
                TranscriptEntry(
                    start=_ts_to_sec(ts_match.group(1)),
                    end=_ts_to_sec(ts_match.group(2)),
                    text=" ".join(text_parts),
                )
            )
    return entries


def fetch_transcript(url: str) -> list[TranscriptEntry]:
    with tempfile.TemporaryDirectory(prefix="ss_tr_") as tmpdir:
        out_tmpl = str(Path(tmpdir) / "subs")
        result = subprocess.run(
            [
                *ytdlp_argv(),
                *ytdlp_extra_argv(),
                "--skip-download",
                "--write-auto-subs",
                "--write-subs",
                "--sub-lang",
                "en.*,en,en-US,en-GB",
                "--sub-format",
                "vtt/srt/best",
                "--output",
                out_tmpl,
                url,
            ],
            capture_output=True,
            text=True,
            timeout=120,
            env=subprocess_env(),
        )
        for path in sorted(Path(tmpdir).iterdir()):
            suffix = path.suffix.lower().lstrip(".")
            if suffix in _CAPTION_SUFFIXES:
                entries = _parse_captions(
                    path.read_text(encoding="utf-8", errors="replace"),
                    "srt" if suffix == "srt" else "vtt",
                )
                if entries:
                    return entries
        if result.returncode != 0:
            stderr = (result.stderr or "")[-600:].lower()
            if "no subtitles" in stderr or "no closed captions" in stderr:
                return []
            raise RuntimeError(
                "Could not fetch transcript — yt-dlp returned an error. "
                "Check that the URL is valid and the VOD is accessible."
            )
        return []


def _video_duration_sec(url: str) -> float:
    result = subprocess.run(
        [*ytdlp_argv(), *ytdlp_extra_argv(), "--no-playlist", "--print", "duration", url],
        capture_output=True,
        text=True,
        timeout=60,
        env=subprocess_env(),
    )
    try:
        return float(result.stdout.strip())
    except ValueError:
        return 0.0


def _find_audio_file(tmpdir: str, stem: str | None = None) -> Path | None:
    for path in Path(tmpdir).iterdir():
        if path.suffix.lower() not in _AUDIO_SUFFIXES:
            continue
        if stem is None or path.stem == stem:
            return path
    return None


def _download_audio_section(
    args: tuple[str, float, float, str, int],
) -> tuple[Path, float] | None:
    url, start, end, tmpdir, idx = args
    stem = f"chunk_{idx:04d}"
    out_stem = str(Path(tmpdir) / stem)
    result = subprocess.run(
        [
            *ytdlp_argv(),
            *ytdlp_extra_argv(),
            "--no-playlist",
            "--format",
            _YTDLP_AUDIO,
            "--extract-audio",
            "--audio-format",
            "mp3",
            "--audio-quality",
            "5",
            "--download-sections",
            f"*{start}-{end}",
            "--output",
            out_stem,
            url,
        ],
        capture_output=True,
        text=True,
        timeout=600,
        env=subprocess_env(),
    )
    found = _find_audio_file(tmpdir, stem)
    if found:
        return found, start
    if result.returncode != 0:
        LOG.warning("audio download failed idx=%d: %s", idx, (result.stderr or "")[-300:])
    return None


def _get_whisper_model(model_size: str, cpu_threads: int) -> object:
    from faster_whisper import WhisperModel  # type: ignore[import-untyped]

    key = (model_size, cpu_threads)
    if getattr(_tl, "model_key", None) != key:
        _tl.model = WhisperModel(
            model_size, device="cpu", compute_type="int8", cpu_threads=cpu_threads
        )
        _tl.model_key = key
    return _tl.model


def _transcribe_chunk(args: tuple[str, float, str, int]) -> list[TranscriptEntry]:
    chunk_path, start_offset, model_size, threads = args
    model = _get_whisper_model(model_size, threads)
    segments, _ = model.transcribe(chunk_path, beam_size=1, vad_filter=True)
    return [
        TranscriptEntry(
            start=round(seg.start + start_offset, 3),
            end=round(seg.end + start_offset, 3),
            text=(seg.text or "").strip(),
        )
        for seg in segments
        if (seg.text or "").strip()
    ]


def _chunk_boundaries(duration: float, chunk_sec: float) -> list[tuple[float, float]]:
    boundaries: list[tuple[float, float]] = []
    t = 0.0
    while t < duration:
        boundaries.append((t, min(t + chunk_sec, duration)))
        t += chunk_sec
    return boundaries


def _download_audio_chunks(
    url: str,
    tmpdir: str,
    duration: float,
    on_progress: Callable[[dict], None] | None,
) -> list[tuple[Path, float]]:
    workers = max(1, _WHISPER_WORKERS)
    if duration <= _WHISPER_CHUNK_SEC or workers == 1:
        on_progress and on_progress(
            {"phase": "downloading", "done": 0, "total": 1, "msg": "Downloading audio…"}
        )
        out_stem = str(Path(tmpdir) / "audio")
        result = subprocess.run(
            [
                *ytdlp_argv(),
                *ytdlp_extra_argv(),
                "--no-playlist",
                "--format",
                _YTDLP_AUDIO,
                "--extract-audio",
                "--audio-format",
                "mp3",
                "--audio-quality",
                "5",
                "--output",
                out_stem,
                url,
            ],
            capture_output=True,
            text=True,
            timeout=600,
            env=subprocess_env(),
        )
        found = _find_audio_file(tmpdir)
        if not found or not found.is_file():
            stderr = (result.stderr or "")[-600:]
            raise RuntimeError(f"Audio download failed. {stderr}")
        on_progress and on_progress(
            {"phase": "downloading", "done": 1, "total": 1, "msg": "Audio downloaded."}
        )
        return [(found, 0.0)]

    boundaries = _chunk_boundaries(duration, _WHISPER_CHUNK_SEC)
    total = len(boundaries)
    dl_args = [(url, start, end, tmpdir, i) for i, (start, end) in enumerate(boundaries)]
    on_progress and on_progress(
        {
            "phase": "downloading",
            "done": 0,
            "total": total,
            "msg": f"Downloading audio in {total} parallel sections…",
        }
    )
    chunks: list[tuple[Path, float]] = []
    done = 0
    with concurrent.futures.ThreadPoolExecutor(max_workers=min(_WHISPER_DL_WORKERS, total)) as pool:
        futures = {pool.submit(_download_audio_section, args): args for args in dl_args}
        for future in concurrent.futures.as_completed(futures):
            done += 1
            if chunk := future.result():
                chunks.append(chunk)
            on_progress and on_progress(
                {
                    "phase": "downloading",
                    "done": done,
                    "total": total,
                    "msg": f"Downloaded {done}/{total} sections…",
                }
            )
    return chunks


def _transcribe_chunks(
    chunks: list[tuple[Path, float]],
    on_progress: Callable[[dict], None] | None,
) -> list[TranscriptEntry]:
    total = len(chunks)
    threads_per = max(1, _CPU // max(1, _WHISPER_WORKERS))
    chunk_args = [(str(path), offset, _WHISPER_MODEL, threads_per) for path, offset in chunks]
    on_progress and on_progress(
        {
            "phase": "transcribing",
            "done": 0,
            "total": total,
            "msg": f"Transcribing {total} chunks ({_WHISPER_MODEL})…",
        }
    )

    workers = min(max(1, _WHISPER_WORKERS), total)
    if workers == 1:
        entries = _transcribe_chunk(chunk_args[0])
        on_progress and on_progress(
            {"phase": "transcribing", "done": 1, "total": 1, "msg": "Done."}
        )
        return entries

    entries: list[TranscriptEntry] = []
    done = 0
    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(_transcribe_chunk, args): args for args in chunk_args}
        for future in concurrent.futures.as_completed(futures):
            done += 1
            entries.extend(future.result())
            on_progress and on_progress(
                {
                    "phase": "transcribing",
                    "done": done,
                    "total": total,
                    "msg": f"Transcribed {done}/{total}…",
                }
            )
    return entries


def whisper_transcribe(
    url: str,
    on_progress: Callable[[dict], None] | None = None,
) -> list[TranscriptEntry]:
    try:
        import faster_whisper  # type: ignore[import-untyped]  # noqa: F401
    except ImportError as exc:
        raise RuntimeError("faster-whisper is not installed. Run: uv sync --extra whisper") from exc

    with tempfile.TemporaryDirectory(prefix="ss_whisper_") as tmpdir:
        on_progress and on_progress({"phase": "probing", "msg": "Fetching video duration…"})
        duration = _video_duration_sec(url)
        chunks = _download_audio_chunks(url, tmpdir, duration, on_progress)
        if not chunks:
            raise RuntimeError("All audio section downloads failed.")
        entries = _transcribe_chunks(chunks, on_progress)

    entries.sort(key=lambda entry: entry.start)
    return entries


def _tokenize(text: str) -> list[str]:
    return re.findall(r"[a-z0-9']+", text.lower())


def _build_windows(
    entries: list[TranscriptEntry],
    window_sec: float,
    step_sec: float,
    min_dur: float,
) -> list[tuple[float, float, str]]:
    if not entries:
        return []
    duration = entries[-1].end
    windows: list[tuple[float, float, str]] = []
    t = 0.0
    while t < duration:
        end = t + window_sec
        parts = [e.text for e in entries if e.start >= t - min_dur and e.start < end]
        if parts:
            windows.append((t, min(end, duration), " ".join(parts)))
        t += step_sec
    return windows


def _score_window(window_text: str, query_tokens: list[str], query_phrase: str) -> float:
    if not query_tokens:
        return 0.0
    words = _tokenize(window_text)
    if not words:
        return 0.0
    word_set = set(words)
    coverage = sum(1 for token in query_tokens if token in word_set) / len(query_tokens)
    tf_sum = sum(words.count(token) for token in query_tokens)
    tf = min(tf_sum / len(words) * 10, 1.0)
    phrase_bonus = (
        0.4 if len(query_phrase) > 3 and query_phrase.lower() in window_text.lower() else 0.0
    )
    return min(0.5 * coverage + 0.2 * tf + phrase_bonus, 1.0)


def _highlight(window_text: str, query_tokens: list[str], max_len: int = 160) -> str:
    sentences = re.split(r"[.?!]\s+", window_text)
    best = max(
        sentences,
        key=lambda sentence: sum(1 for token in query_tokens if token in _tokenize(sentence)),
        default=window_text,
    )
    if len(best) > max_len:
        best = best[:max_len].rsplit(" ", 1)[0] + "…"
    return best.strip()


def search_transcript(
    entries: list[TranscriptEntry],
    query: str,
    *,
    n: int = 8,
    window_sec: float = 30.0,
    step_sec: float = 15.0,
    clip_buffer_before: float = 3.0,
    clip_buffer_after: float = 5.0,
    min_score: float = 0.05,
) -> list[SearchResult]:
    query = query.strip()
    if not query or not entries:
        return []

    query_tokens = _tokenize(query)
    scored: list[tuple[float, float, float, str]] = []
    for start, end, text in _build_windows(entries, window_sec, step_sec, 0.5):
        score = _score_window(text, query_tokens, query)
        if score >= min_score:
            scored.append((score, start, end, text))
    scored.sort(key=lambda row: -row[0])

    results: list[SearchResult] = []
    used: list[tuple[float, float]] = []
    for score, start, end, text in scored:
        if len(results) >= n:
            break
        if any(max(start, u0) < min(end, u1) - window_sec * 0.5 for u0, u1 in used):
            continue
        used.append((start, end))
        results.append(
            SearchResult(
                start=round(max(0.0, start - clip_buffer_before), 2),
                end=round(end + clip_buffer_after, 2),
                text=text,
                score=round(score, 4),
                context=_highlight(text, query_tokens),
            )
        )
    return results
