import os
import re
import json
import math
import time
import shutil
import zipfile
import tempfile
import subprocess
from pathlib import Path
from typing import Dict, List, Tuple, Optional, Any

import pandas as pd
import streamlit as st

APP_NAME = "Reptile Clip Master"
DEFAULT_HASHTAGS = [
    "#tiktokde", "#deutschertiktok", "#streamer", "#twitchde", "#comedydeutsch",
    "#gamingdeutsch", "#reelsdeutsch", "#fyp", "#viral", "#fürdich",
]

COMEDY_TERMS = [
    "haha", "hahaha", "lach", "lachen", "alter", "digga", "digger", "bruder", "bro",
    "junge", "wtf", "was zur", "hä", "ey", "lol", "krank", "wild", "komplett",
    "ich schwöre", "oh mein gott", "omg", "chat", "clip", "beleidigt", "ausrasten",
    "ausgerastet", "schreit", "schreien", "tot", "bodenlos", "peinlich", "cringe",
    "lost", "unangenehm", "random", "niemals", "nicht normal", "eskaliert", "eskalation",
]
DRAMA_TERMS = [
    "stress", "problem", "kaputt", "verloren", "verliere", "fail", "fehler", "gebannt",
    "ban", "beleidigt", "rage", "wütend", "angst", "peinlich", "dumm", "scheiße",
    "scheisse", "gefährlich", "verrückt", "krank", "cringe", "hass", "lügt", "fake",
]
HOOK_TERMS = [
    "warum", "wie", "was", "niemals", "ich schwöre", "das ist", "das war", "guck",
    "pass auf", "chat", "alter", "digga", "bro", "mein leben", "nicht normal", "größte",
    "schlimmste", "bester", "wildeste", "peinlichste", "plot twist", "keiner", "alle",
]
LOW_VALUE_STARTS = [
    "und", "aber", "also", "äh", "ähm", "hm", "okay", "ja", "ne", "so", "dann", "weil",
]
STOPWORDS = set("""
aber als am an auch auf aus bei bin bist da das dass dein deine dem den der des die dir doch du durch ein eine einem einen einer eines er es für haben habe habt hat hier ich im in ist ja kann kein keine man mein meine mich mit muss nach nicht noch nur oder schon sehr sein seid sind so um und uns vom von vor war warum was wenn wer wie wir wird wo zu zum zur über
""".split())

st.set_page_config(page_title=APP_NAME, page_icon="🐍", layout="wide")

st.markdown(
    """
    <style>
    .block-container {padding-top: 1.1rem; padding-bottom: 2rem;}
    .rv-card {border: 1px solid rgba(128,128,128,.22); border-radius: 18px; padding: 1rem; margin: .7rem 0; background: rgba(128,128,128,.055);}
    .rv-score {font-size: 2.1rem; font-weight: 800; line-height: 1;}
    .rv-muted {opacity: .75; font-size: .92rem;}
    .rv-pill {display:inline-block; padding:.18rem .55rem; border-radius:999px; border:1px solid rgba(128,128,128,.25); margin:.1rem .18rem .1rem 0; font-size:.82rem;}
    </style>
    """,
    unsafe_allow_html=True,
)


def clean_text(text: str) -> str:
    text = re.sub(r"\s+", " ", text or "").strip()
    return text


def safe_name(name: str, fallback: str = "source") -> str:
    name = re.sub(r"[^a-zA-Z0-9_.-]+", "_", name.strip())
    return name[:90] or fallback


def run_cmd(cmd: List[str], timeout: Optional[int] = None) -> Tuple[bool, str]:
    try:
        proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, timeout=timeout)
        return proc.returncode == 0, proc.stdout[-6000:]
    except subprocess.TimeoutExpired:
        return False, "Command timed out. Try a shorter source or run locally."
    except FileNotFoundError as exc:
        return False, f"Missing binary: {exc}"
    except Exception as exc:
        return False, str(exc)


def seconds_to_stamp(seconds: float) -> str:
    seconds = max(0.0, float(seconds))
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = seconds % 60
    return f"{h:02d}:{m:02d}:{s:06.3f}".replace(".", ",")


def display_stamp(seconds: float) -> str:
    seconds = max(0.0, float(seconds))
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = int(seconds % 60)
    if h:
        return f"{h}:{m:02d}:{s:02d}"
    return f"{m}:{s:02d}"


def ffprobe_duration(path: Path) -> Optional[float]:
    ok, out = run_cmd([
        "ffprobe", "-v", "error", "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1", str(path)
    ])
    if ok:
        try:
            return float(out.strip().splitlines()[-1])
        except Exception:
            return None
    return None


def ffprobe_video_stream(path: Path) -> Dict[str, Any]:
    ok, out = run_cmd([
        "ffprobe", "-v", "error", "-select_streams", "v:0",
        "-show_entries", "stream=width,height", "-of", "json", str(path)
    ])
    if not ok:
        return {"has_video": False}
    try:
        data = json.loads(out)
        streams = data.get("streams", [])
        if not streams:
            return {"has_video": False}
        return {"has_video": True, "width": streams[0].get("width"), "height": streams[0].get("height")}
    except Exception:
        return {"has_video": False}


def save_upload(uploaded_file, workdir: Path) -> Path:
    target = workdir / safe_name(uploaded_file.name, "upload.bin")
    with open(target, "wb") as f:
        f.write(uploaded_file.getbuffer())
    return target


def download_url(url: str, workdir: Path, max_minutes: int) -> Tuple[Optional[Path], str]:
    target = workdir / "downloaded_source.%(ext)s"
    section = f"*0-{int(max_minutes * 60)}" if max_minutes > 0 else "*"
    cmd = [
        "yt-dlp",
        "--no-playlist",
        "--merge-output-format", "mp4",
        "--download-sections", section,
        "-f", "bv*[height<=1080]+ba/b[height<=1080]/b",
        "-o", str(target),
        url.strip(),
    ]
    ok, out = run_cmd(cmd, timeout=max(600, max_minutes * 80 if max_minutes > 0 else 1200))
    if not ok:
        return None, out
    candidates = sorted(workdir.glob("downloaded_source.*"), key=lambda p: p.stat().st_size, reverse=True)
    return (candidates[0] if candidates else None), out


def extract_audio(source: Path, workdir: Path) -> Path:
    audio = workdir / "audio_16k_mono.wav"
    ok, out = run_cmd([
        "ffmpeg", "-y", "-i", str(source), "-vn", "-ac", "1", "-ar", "16000",
        "-af", "loudnorm=I=-16:TP=-1.5:LRA=11", str(audio)
    ], timeout=900)
    if not ok:
        raise RuntimeError(out)
    return audio


@st.cache_resource(show_spinner=False)
def load_whisper_model(model_size: str, compute_type: str):
    from faster_whisper import WhisperModel
    return WhisperModel(model_size, device="cpu", compute_type=compute_type)


def transcribe_audio(audio_path: Path, model_size: str, language: str, compute_type: str, progress=None) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]], Dict[str, Any]]:
    model = load_whisper_model(model_size, compute_type)
    lang = None if language == "auto" else language
    segments_iter, info = model.transcribe(
        str(audio_path),
        language=lang,
        vad_filter=True,
        word_timestamps=True,
        beam_size=5,
        condition_on_previous_text=False,
    )
    segments: List[Dict[str, Any]] = []
    words: List[Dict[str, Any]] = []
    for idx, seg in enumerate(segments_iter):
        text = clean_text(seg.text)
        if not text:
            continue
        item = {
            "start": float(seg.start),
            "end": float(seg.end),
            "text": text,
            "avg_logprob": float(getattr(seg, "avg_logprob", -0.6) or -0.6),
            "no_speech_prob": float(getattr(seg, "no_speech_prob", 0.0) or 0.0),
        }
        segments.append(item)
        if getattr(seg, "words", None):
            for w in seg.words:
                wt = clean_text(getattr(w, "word", ""))
                if wt:
                    words.append({"start": float(w.start), "end": float(w.end), "word": wt})
        if progress and idx % 10 == 0:
            progress.write(f"Transkribiere Segment {idx + 1} …")
    info_dict = {
        "language": getattr(info, "language", None),
        "language_probability": float(getattr(info, "language_probability", 0.0) or 0.0),
        "duration": float(getattr(info, "duration", 0.0) or 0.0),
    }
    return segments, words, info_dict


def text_features(text: str) -> Dict[str, Any]:
    lower = text.lower()
    words = re.findall(r"[a-zA-ZäöüÄÖÜß0-9]+", lower)
    word_count = len(words)

    def count_terms(terms: List[str]) -> int:
        return sum(lower.count(t) for t in terms)

    comedy = count_terms(COMEDY_TERMS)
    drama = count_terms(DRAMA_TERMS)
    hook = count_terms(HOOK_TERMS)
    question = text.count("?") + sum(1 for w in words[:45] if w in {"was", "warum", "wie", "wer", "wo", "wieso"})
    exclaim = text.count("!") + lower.count("niemals") + lower.count("wtf")
    direct_address = sum(lower.count(x) for x in ["chat", "du", "ihr", "bro", "digga", "alter"])
    numbers = len(re.findall(r"\b\d+\b", lower))
    profanity = sum(lower.count(x) for x in ["scheiße", "scheisse", "fuck", "dreck", "hurensohn", "arsch", "kack"])
    return {
        "words": words,
        "word_count": word_count,
        "comedy": comedy,
        "drama": drama,
        "hook": hook,
        "question": question,
        "exclaim": exclaim,
        "direct_address": direct_address,
        "numbers": numbers,
        "profanity": profanity,
    }


def clamp(value: float, low: float = 0, high: float = 100) -> int:
    return int(max(low, min(high, round(value))))


def score_candidate(candidate: Dict[str, Any]) -> Dict[str, Any]:
    text = candidate["text"]
    dur = max(1.0, candidate["end"] - candidate["start"])
    feats = text_features(text)
    wc = feats["word_count"]
    wpm = wc / dur * 60

    first_words = feats["words"][:12]
    first = " ".join(first_words)
    bad_start = bool(first_words and first_words[0] in LOW_VALUE_STARTS)

    hook_score = min(24, feats["hook"] * 5 + feats["question"] * 3 + feats["numbers"] * 2 + (0 if bad_start else 4))
    comedy_score = min(22, feats["comedy"] * 3.2 + feats["exclaim"] * 2.2 + feats["direct_address"] * 1.1)
    drama_score = min(16, feats["drama"] * 3.2 + feats["profanity"] * 1.7)
    pace_score = 0
    if 115 <= wpm <= 230:
        pace_score = 14
    elif 80 <= wpm < 115 or 230 < wpm <= 270:
        pace_score = 9
    else:
        pace_score = 4

    if 22 <= dur <= 55:
        length_score = 14
    elif 15 <= dur < 22 or 55 < dur <= 75:
        length_score = 9
    else:
        length_score = 4

    completeness_score = 10
    if bad_start:
        completeness_score -= 3
    if not re.search(r"[.!?…]$", text.strip()):
        completeness_score -= 2
    if wc < 35:
        completeness_score -= 3

    avg_logprob = candidate.get("avg_logprob", -0.65)
    no_speech = candidate.get("no_speech_prob", 0.0)
    quality_penalty = 0
    if avg_logprob < -1.05:
        quality_penalty += 10
    if no_speech > 0.35:
        quality_penalty += 12
    if wc < 25:
        quality_penalty += 10

    score = 24 + hook_score + comedy_score + drama_score + pace_score + length_score + completeness_score - quality_penalty
    score = clamp(score, 0, 99)

    reasons = []
    if hook_score >= 12:
        reasons.append("starker Einstieg / klare Hook")
    if comedy_score >= 10:
        reasons.append("Comedy- und Reaktionssignale")
    if drama_score >= 7:
        reasons.append("Konflikt/Eskalation statt leerem Gelaber")
    if pace_score >= 9:
        reasons.append(f"gute Sprechdichte ({int(wpm)} Wörter/Min.)")
    if length_score >= 9:
        reasons.append("Shortform-taugliche Länge")
    if quality_penalty:
        reasons.append("Qualität/Verständlichkeit könnte schwächer sein")
    if not reasons:
        reasons.append("brauchbarer Moment, aber nicht brutal genug")

    candidate.update({
        "score": score,
        "wpm": round(wpm, 1),
        "reasons": reasons,
        "features": feats,
        "bad_start": bad_start,
        "quality_penalty": quality_penalty,
    })
    return candidate


def build_candidates(segments: List[Dict[str, Any]], min_len: int, max_len: int, top_n: int) -> List[Dict[str, Any]]:
    candidates: List[Dict[str, Any]] = []
    n = len(segments)
    if not n:
        return []

    for i in range(n):
        texts = []
        logprobs = []
        no_speeches = []
        start = segments[i]["start"]
        for j in range(i, min(n, i + 25)):
            texts.append(segments[j]["text"])
            logprobs.append(segments[j].get("avg_logprob", -0.65))
            no_speeches.append(segments[j].get("no_speech_prob", 0.0))
            end = segments[j]["end"]
            dur = end - start
            if dur > max_len:
                break
            if dur >= min_len:
                # Save only sensible endings or every few segments after min length.
                joined = clean_text(" ".join(texts))
                if j == n - 1 or re.search(r"[.!?…]$", joined) or dur > (min_len + 10) or (j - i) % 4 == 0:
                    cand = {
                        "start": max(0.0, start - 0.35),
                        "end": end + 0.45,
                        "text": joined,
                        "segment_start_index": i,
                        "segment_end_index": j,
                        "avg_logprob": sum(logprobs) / max(1, len(logprobs)),
                        "no_speech_prob": sum(no_speeches) / max(1, len(no_speeches)),
                    }
                    candidates.append(score_candidate(cand))

    # Remove near-duplicates by time overlap.
    candidates.sort(key=lambda x: x["score"], reverse=True)
    selected: List[Dict[str, Any]] = []
    for cand in candidates:
        overlap_bad = False
        for prev in selected:
            overlap = max(0, min(cand["end"], prev["end"]) - max(cand["start"], prev["start"]))
            smaller = max(1, min(cand["end"] - cand["start"], prev["end"] - prev["start"]))
            if overlap / smaller > 0.55:
                overlap_bad = True
                break
        if not overlap_bad:
            selected.append(cand)
        if len(selected) >= top_n:
            break
    return selected


def keyword_hashtags(text: str) -> List[str]:
    lower = text.lower()
    tags = []
    mapping = {
        "chat": "#twitchchat",
        "minecraft": "#minecraftdeutsch",
        "fortnite": "#fortnitedeutsch",
        "gta": "#gtadeutsch",
        "discord": "#discorddeutsch",
        "irl": "#irldeutsch",
        "beleidigt": "#streamermoment",
        "ausrasten": "#rageclip",
        "rage": "#rageclip",
        "cringe": "#cringe",
        "fail": "#fail",
        "lachen": "#lustig",
        "haha": "#lustig",
        "wild": "#wild",
    }
    for key, tag in mapping.items():
        if key in lower and tag not in tags:
            tags.append(tag)
    words = [w for w in re.findall(r"[a-zA-ZäöüÄÖÜß]{4,}", lower) if w not in STOPWORDS]
    freq: Dict[str, int] = {}
    for w in words:
        freq[w] = freq.get(w, 0) + 1
    for word, _ in sorted(freq.items(), key=lambda x: x[1], reverse=True)[:3]:
        tag = "#" + word.replace("ß", "ss")
        if tag not in tags and len(tag) <= 24:
            tags.append(tag)
    result = []
    for tag in tags + DEFAULT_HASHTAGS:
        if tag not in result:
            result.append(tag)
    return result[:14]


def make_title(candidate: Dict[str, Any], creator_style: str) -> str:
    text = candidate["text"]
    lower = text.lower()
    if "chat" in lower and any(x in lower for x in ["beleidigt", "roast", "fertig", "zerstört", "ausrast"]):
        return "Mein Chat hat mich komplett zerstört"
    if any(x in lower for x in ["ausrast", "rage", "schrei", "wütend"]):
        return "Ich bin komplett ausgerastet"
    if any(x in lower for x in ["niemals", "wtf", "was zur", "oh mein gott"]):
        return "Dieser Moment war nicht normal"
    if any(x in lower for x in ["peinlich", "cringe", "unangenehm"]):
        return "Das war viel zu unangenehm"
    if any(x in lower for x in ["fail", "verloren", "kaputt", "fehler"]):
        return "Das ist komplett schiefgelaufen"
    words = re.findall(r"[a-zA-ZäöüÄÖÜß0-9]+", text)
    short = " ".join(words[:7]).strip()
    if short:
        return f"{short}…"
    return "Der wildeste Stream-Moment"


def make_description(candidate: Dict[str, Any], title: str, creator_style: str) -> str:
    reason = ", ".join(candidate.get("reasons", [])[:2])
    if creator_style == "Hart / frech":
        return f"{title}. Genau solche Momente machen Streams gefährlich gut: {reason}. Folge, wenn du mehr deutsche Chaos-Clips willst."
    if creator_style == "Story / persönlich":
        return f"{title}. Der Clip funktioniert, weil er direkt Spannung aufbaut und sich wie ein echter Live-Moment anfühlt: {reason}."
    return f"{title}. Live-Moment mit guter Shortform-Chance: {reason}."


def make_overlay_hook(candidate: Dict[str, Any]) -> str:
    score = candidate.get("score", 0)
    lower = candidate["text"].lower()
    if score >= 85:
        base = "DIESER MOMENT WAR NICHT NORMAL"
    elif "chat" in lower:
        base = "MEIN CHAT WAR ZU WILD"
    elif any(x in lower for x in ["fail", "verloren", "kaputt"]):
        base = "DAS IST KOMPLETT SCHIEF GEGANGEN"
    elif any(x in lower for x in ["beleidigt", "roast", "dumm"]):
        base = "ICH WURDE LIVE ZERSTÖRT"
    else:
        base = "DAS MUSSTE EIN CLIP WERDEN"
    return base


def enrich_candidates(candidates: List[Dict[str, Any]], creator_style: str) -> List[Dict[str, Any]]:
    for idx, cand in enumerate(candidates, start=1):
        title = make_title(cand, creator_style)
        cand["rank"] = idx
        cand["title"] = title
        cand["overlay_hook"] = make_overlay_hook(cand)
        cand["description"] = make_description(cand, title, creator_style)
        cand["hashtags"] = keyword_hashtags(cand["text"])
        cand["filename"] = f"clip_{idx:02d}_{cand['score']:02d}_{safe_name(title.lower())}.mp4"
        cand["duration"] = round(cand["end"] - cand["start"], 2)
    return candidates


def srt_timestamp(seconds: float) -> str:
    return seconds_to_stamp(seconds)


def write_clip_srt(words: List[Dict[str, Any]], clip: Dict[str, Any], path: Path) -> None:
    start = clip["start"]
    end = clip["end"]
    clip_words = [w for w in words if w["end"] >= start and w["start"] <= end]
    if not clip_words:
        # Fallback: Split transcript into chunks over clip duration.
        raw_words = re.findall(r"\S+", clip["text"])
        dur = max(1.0, end - start)
        step = dur / max(1, len(raw_words))
        clip_words = []
        for i, word in enumerate(raw_words):
            clip_words.append({"start": start + i * step, "end": start + (i + 1) * step, "word": word})

    blocks = []
    i = 0
    while i < len(clip_words):
        group = clip_words[i:i + 5]
        txt = " ".join(w["word"] for w in group).strip()
        if not txt:
            i += 5
            continue
        stime = max(0.0, group[0]["start"] - start)
        etime = max(stime + 0.8, group[-1]["end"] - start)
        etime = min(etime + 0.15, end - start)
        blocks.append((stime, etime, txt.upper()))
        i += 5

    with open(path, "w", encoding="utf-8") as f:
        for idx, (a, b, txt) in enumerate(blocks, start=1):
            f.write(f"{idx}\n{srt_timestamp(a)} --> {srt_timestamp(b)}\n{txt}\n\n")


def make_captionless_clip(source: Path, clip: Dict[str, Any], out_path: Path, vertical: bool) -> Tuple[bool, str]:
    start = clip["start"]
    dur = max(1.0, clip["end"] - clip["start"])
    if vertical:
        vf = (
            "[0:v]scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,gblur=sigma=32[bg];"
            "[0:v]scale=1080:1920:force_original_aspect_ratio=decrease[fg];"
            "[bg][fg]overlay=(W-w)/2:(H-h)/2"
        )
        cmd = [
            "ffmpeg", "-y", "-ss", str(start), "-t", str(dur), "-i", str(source),
            "-filter_complex", vf,
            "-c:v", "libx264", "-preset", "veryfast", "-crf", "23",
            "-c:a", "aac", "-b:a", "160k", "-movflags", "+faststart", str(out_path)
        ]
    else:
        cmd = [
            "ffmpeg", "-y", "-ss", str(start), "-t", str(dur), "-i", str(source),
            "-c:v", "libx264", "-preset", "veryfast", "-crf", "23",
            "-c:a", "aac", "-b:a", "160k", "-movflags", "+faststart", str(out_path)
        ]
    return run_cmd(cmd, timeout=900)


def make_burned_caption_clip(source: Path, clip: Dict[str, Any], srt_path: Path, out_path: Path, vertical: bool) -> Tuple[bool, str]:
    start = clip["start"]
    dur = max(1.0, clip["end"] - clip["start"])
    # Escape Windows/Unix chars for ffmpeg subtitles filter.
    srt_filter_path = str(srt_path).replace("\\", "/").replace(":", "\\:").replace("'", "\\'")
    style = "FontName=Arial,FontSize=15,PrimaryColour=&H00FFFFFF,OutlineColour=&H00000000,BorderStyle=1,Outline=3,Shadow=1,Alignment=2,MarginV=190"
    sub = f"subtitles='{srt_filter_path}':force_style='{style}'"
    if vertical:
        vf = (
            "[0:v]scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,gblur=sigma=32[bg];"
            "[0:v]scale=1080:1920:force_original_aspect_ratio=decrease[fg];"
            f"[bg][fg]overlay=(W-w)/2:(H-h)/2,{sub}"
        )
        cmd = [
            "ffmpeg", "-y", "-ss", str(start), "-t", str(dur), "-i", str(source),
            "-filter_complex", vf,
            "-c:v", "libx264", "-preset", "veryfast", "-crf", "23",
            "-c:a", "aac", "-b:a", "160k", "-movflags", "+faststart", str(out_path)
        ]
    else:
        cmd = [
            "ffmpeg", "-y", "-ss", str(start), "-t", str(dur), "-i", str(source),
            "-vf", sub,
            "-c:v", "libx264", "-preset", "veryfast", "-crf", "23",
            "-c:a", "aac", "-b:a", "160k", "-movflags", "+faststart", str(out_path)
        ]
    return run_cmd(cmd, timeout=900)


def write_metadata(candidates: List[Dict[str, Any]], out_dir: Path) -> Tuple[Path, Path]:
    rows = []
    for c in candidates:
        rows.append({
            "rank": c["rank"],
            "score": c["score"],
            "start": display_stamp(c["start"]),
            "end": display_stamp(c["end"]),
            "duration_sec": c["duration"],
            "title": c["title"],
            "overlay_hook": c["overlay_hook"],
            "description": c["description"],
            "hashtags": " ".join(c["hashtags"]),
            "why": "; ".join(c["reasons"]),
            "transcript": c["text"],
            "filename": c["filename"],
        })
    df = pd.DataFrame(rows)
    csv_path = out_dir / "clip_plan.csv"
    json_path = out_dir / "clip_plan.json"
    df.to_csv(csv_path, index=False, encoding="utf-8-sig")
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(rows, f, ensure_ascii=False, indent=2)
    return csv_path, json_path


def zip_folder(folder: Path, zip_path: Path) -> Path:
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for file in folder.rglob("*"):
            if file.is_file():
                zf.write(file, file.relative_to(folder))
    return zip_path


def render_score_badge(score: int) -> str:
    if score >= 85:
        label = "Elite"
    elif score >= 72:
        label = "Sehr stark"
    elif score >= 60:
        label = "Brauchbar"
    else:
        label = "Schwach"
    return f"<div class='rv-score'>{score}/99</div><div class='rv-muted'>{label}</div>"


def show_clip_card(c: Dict[str, Any]) -> None:
    st.markdown("<div class='rv-card'>", unsafe_allow_html=True)
    col1, col2 = st.columns([1, 4])
    with col1:
        st.markdown(render_score_badge(c["score"]), unsafe_allow_html=True)
        st.caption(f"{display_stamp(c['start'])}–{display_stamp(c['end'])} · {int(c['duration'])}s")
    with col2:
        st.subheader(f"#{c['rank']} {c['title']}")
        st.markdown(f"**Overlay:** `{c['overlay_hook']}`")
        st.write(c["description"])
        st.markdown(" ".join([f"<span class='rv-pill'>{tag}</span>" for tag in c["hashtags"]]), unsafe_allow_html=True)
        st.markdown("**Warum stark:** " + "; ".join(c["reasons"]))
        with st.expander("Transkript anzeigen"):
            st.write(c["text"])
    st.markdown("</div>", unsafe_allow_html=True)


def main():
    st.title("🐍 Reptile Clip Master")
    st.caption("Deutsch-first Stream-zu-Shorts-Tool: Transkript, Clip-Auswahl, Score, Titel, Beschreibung, Hashtags und Export.")

    with st.sidebar:
        st.header("Input")
        input_mode = st.radio("Quelle", ["Datei hochladen", "Twitch/YouTube/VOD-Link"], index=0)
        uploaded = None
        url = ""
        if input_mode == "Datei hochladen":
            uploaded = st.file_uploader("MP4/MOV/MKV/WEBM/MP3/M4A/WAV", type=["mp4", "mov", "mkv", "webm", "mp3", "m4a", "wav"])
        else:
            url = st.text_input("VOD-Link", placeholder="https://www.twitch.tv/videos/...")
            max_minutes = st.slider("Max. Minuten herunterladen", 5, 180, 45, help="Auf Streamlit Cloud klein halten. Lokal kannst du höher gehen.")

        st.header("Analyse")
        language = st.selectbox("Sprache", ["de", "auto", "en"], index=0)
        model_size = st.selectbox("Whisper-Modell", ["tiny", "base", "small"], index=1, help="tiny = schneller, small = genauer aber schwerer.")
        compute_type = st.selectbox("CPU-Modus", ["int8", "float32"], index=0)
        min_len = st.slider("Min. Clip-Länge", 8, 45, 18)
        max_len = st.slider("Max. Clip-Länge", 25, 120, 65)
        top_n = st.slider("Anzahl Clips", 3, 20, 8)
        creator_style = st.selectbox("Caption-Stil", ["Hart / frech", "Neutral", "Story / persönlich"], index=0)

        st.header("Export")
        export_video = st.checkbox("MP4-Clips rendern", value=True)
        vertical = st.checkbox("9:16 TikTok/Reels mit Blur-Background", value=True)
        burn_captions = st.checkbox("Untertitel ins Video brennen", value=False, help="Kann auf Cloud je nach FFmpeg/libass scheitern. SRT wird immer erzeugt.")
        run_button = st.button("Clips analysieren", type="primary", use_container_width=True)

    st.info("Real Talk: Kein Tool kann Performance garantieren. Dieses Tool priorisiert starke Hooks, Eskalation, Comedy-Signale, klare Länge und Verständlichkeit. Die Scores sind eine Sortierhilfe, kein Orakel.")

    if not run_button:
        st.markdown(
            """
            ### Was dieses Tool macht
            1. Nimmt MP4/Audio oder einen VOD-Link.
            2. Transkribiert Deutsch/Englisch lokal mit Whisper.
            3. Findet Kandidaten für TikTok/Reels/Shorts.
            4. Scored jeden Clip nach Hook, Comedy, Eskalation, Pace, Länge und Verständlichkeit.
            5. Gibt Titel, Overlay-Hook, Beschreibung, Hashtags und Begründung aus.
            6. Rendert optional MP4-Clips und SRT-Untertitel.
            """
        )
        return

    if input_mode == "Datei hochladen" and uploaded is None:
        st.error("Lad zuerst eine Datei hoch.")
        return
    if input_mode != "Datei hochladen" and not url.strip():
        st.error("Füg zuerst einen VOD-Link ein.")
        return
    if min_len >= max_len:
        st.error("Min. Clip-Länge muss kleiner als Max. Clip-Länge sein.")
        return

    session_root = Path(tempfile.mkdtemp(prefix="reptile_clips_"))
    workdir = session_root / "work"
    out_dir = session_root / "exports"
    workdir.mkdir(parents=True, exist_ok=True)
    out_dir.mkdir(parents=True, exist_ok=True)

    try:
        status = st.empty()
        status.write("Quelle vorbereiten …")
        if input_mode == "Datei hochladen":
            source = save_upload(uploaded, workdir)
        else:
            source, log = download_url(url, workdir, max_minutes=max_minutes)
            if source is None:
                st.error("Download fehlgeschlagen. Bei Twitch kann das an Login/Region/gelöschtem VOD/zu großem VOD liegen.")
                st.code(log)
                return

        duration = ffprobe_duration(source)
        video_info = ffprobe_video_stream(source)
        if duration:
            st.success(f"Quelle geladen: {source.name} · Dauer ca. {display_stamp(duration)}")
        else:
            st.success(f"Quelle geladen: {source.name}")

        status.write("Audio extrahieren …")
        audio = extract_audio(source, workdir)

        status.write("Transkript erstellen …")
        transcribe_box = st.empty()
        segments, words, info = transcribe_audio(audio, model_size, language, compute_type, progress=transcribe_box)
        transcribe_box.empty()
        if not segments:
            st.error("Kein brauchbares Transkript gefunden. Prüfe Audio, Sprache oder Modellgröße.")
            return

        full_transcript = clean_text(" ".join(s["text"] for s in segments))
        with open(out_dir / "full_transcript.txt", "w", encoding="utf-8") as f:
            f.write(full_transcript)

        status.write("Clip-Momente bewerten …")
        candidates = build_candidates(segments, min_len=min_len, max_len=max_len, top_n=top_n)
        candidates = enrich_candidates(candidates, creator_style=creator_style)
        if not candidates:
            st.error("Keine Clip-Kandidaten gefunden. Setz Min. Clip-Länge niedriger oder prüfe das Transkript.")
            return

        csv_path, json_path = write_metadata(candidates, out_dir)

        if export_video:
            if not video_info.get("has_video"):
                st.warning("Quelle hat keinen Videostream. Ich exportiere deshalb nur SRT + Plan, keine MP4-Clips.")
            else:
                progress = st.progress(0)
                for idx, clip in enumerate(candidates, start=1):
                    srt_path = out_dir / clip["filename"].replace(".mp4", ".srt")
                    write_clip_srt(words, clip, srt_path)
                    out_path = out_dir / clip["filename"]
                    status.write(f"Rendere Clip {idx}/{len(candidates)} …")
                    if burn_captions:
                        ok, log = make_burned_caption_clip(source, clip, srt_path, out_path, vertical=vertical)
                        if not ok:
                            # Fallback without burned captions.
                            fallback = out_dir / clip["filename"].replace(".mp4", "_no_burn.mp4")
                            ok2, log2 = make_captionless_clip(source, clip, fallback, vertical=vertical)
                            if ok2:
                                clip["filename"] = fallback.name
                                st.warning(f"Untertitel-Burn für Clip {idx} fehlgeschlagen. Fallback ohne eingebrannte Captions erstellt.")
                            else:
                                st.error(f"Clip {idx} konnte nicht gerendert werden.")
                                st.code(log + "\n" + log2)
                    else:
                        ok, log = make_captionless_clip(source, clip, out_path, vertical=vertical)
                        if not ok:
                            st.error(f"Clip {idx} konnte nicht gerendert werden.")
                            st.code(log)
                    progress.progress(idx / len(candidates))
        else:
            for clip in candidates:
                srt_path = out_dir / clip["filename"].replace(".mp4", ".srt")
                write_clip_srt(words, clip, srt_path)

        status.empty()
        st.success("Analyse fertig.")

        st.subheader("Beste Clips")
        for c in candidates:
            show_clip_card(c)

        st.subheader("Clip-Plan")
        plan_df = pd.read_csv(csv_path)
        st.dataframe(plan_df, use_container_width=True)

        zip_path = session_root / "reptile_clip_master_exports.zip"
        zip_folder(out_dir, zip_path)
        with open(zip_path, "rb") as f:
            st.download_button(
                "Alles als ZIP herunterladen",
                data=f,
                file_name="reptile_clip_master_exports.zip",
                mime="application/zip",
                type="primary",
            )

        with st.expander("Transkript anzeigen"):
            st.write(full_transcript)
            st.json(info)

    except Exception as exc:
        st.error("Abbruch. Das ist meistens Quelle zu groß, FFmpeg fehlt, Whisper-Modell zu schwer oder Streamlit Cloud hat Ressourcen gekillt.")
        st.exception(exc)
    finally:
        # Do not delete immediately; Streamlit needs the download button files during this run.
        pass


if __name__ == "__main__":
    main()
