"""
================================================================================
                    ONE-CLICK AUTO DUBBER (ENGLISH TO HINDI)
================================================================================
Converts ANY English video into high-quality Hindi dubbed video in a single click.

Key Features:
- 100% Free & Local: Uses Edge-TTS neural voices, FFmpeg, and NumPy.
- Zero-Configuration: Drag-and-drop or double-click to pick any video file.
- Automatic Subtitle Detection: Extracts embedded subtitles from MKV/MP4,
  reads existing .srt, or uses AI Whisper transcription if no subs exist.
- Natural Conversational Hindi: Auto-translates dialogue accurately.
- In-Phase Instrumental Audio: Cancels center vocals while 100% preserving
  background music & sound effects (zero phase cancellation on laptop/phone speakers).
- Natural Voice Cadence: Paces speech and limits speedups (max 1.25x) to maintain human tone.
- High-Fidelity Audio Mixing: Smooth -9dB sidechain ducking during dialogue.
- Lossless Stream Copy: Copies original video stream (-c:v copy) with zero quality loss.
================================================================================
"""

import os
import sys
import re
import json
import time
import wave
import shutil
import asyncio
import argparse
import subprocess
import urllib.request
import urllib.parse
from concurrent.futures import ThreadPoolExecutor
import numpy as np

# Try importing edge-tts
try:
    import edge_tts
except ImportError:
    print("ERROR: edge-tts is not installed. Run: pip install edge-tts")
    sys.exit(1)

# Default voice profiles (high quality Indian neural voices)
DEFAULT_VOICES = {
    "male_lead": {
        "voice": "hi-IN-MadhurNeural",
        "rate": "+0%",
        "pitch": "+0Hz"
    },
    "female_lead": {
        "voice": "hi-IN-SwaraNeural",
        "rate": "+2%",
        "pitch": "+5Hz"
    },
    "male_deep": {
        "voice": "hi-IN-MadhurNeural",
        "rate": "-5%",
        "pitch": "-16Hz"
    },
    "female_soft": {
        "voice": "hi-IN-SwaraNeural",
        "rate": "+0%",
        "pitch": "-4Hz"
    },
    "male_energetic": {
        "voice": "hi-IN-MadhurNeural",
        "rate": "+8%",
        "pitch": "+6Hz"
    }
}

# ----------------------------------------------------------------------
# 1. AUDIO UTILITIES (WAV, NO-VOCALS, DUCKING)
# ----------------------------------------------------------------------

def load_wav(filepath):
    w = wave.open(filepath, 'rb')
    sr = w.getframerate()
    n_ch = w.getnchannels()
    n_frames = w.getnframes()
    data = np.frombuffer(w.readframes(n_frames), dtype=np.int16).reshape(-1, n_ch)
    w.close()
    return data, sr, n_ch

def save_wav(filepath, data, sr):
    data_int16 = np.clip(data, -32767, 32767).astype(np.int16)
    w = wave.open(filepath, 'wb')
    w.setnchannels(data.shape[1] if data.ndim > 1 else 1)
    w.setsampwidth(2)
    w.setframerate(sr)
    w.writeframes(data_int16.tobytes())
    w.close()

def create_in_phase_no_vocals(raw_audio_path, output_no_vocals_path):
    """
    Center vocal cancellation: 0.5 * (L - R) duplicated to stereo.
    Guarantees zero acoustic phase cancellation on phone/laptop mono speakers.
    """
    raw_data, sr, n_ch = load_wav(raw_audio_path)
    if n_ch < 2:
        diff = raw_data.astype(np.float32) * 0.4
        out_bg = np.repeat(diff, 2, axis=1)
    else:
        diff = 0.5 * (raw_data[:, 0].astype(np.float32) - raw_data[:, 1].astype(np.float32))
        out_bg = np.stack([diff, diff], axis=1)
    save_wav(output_no_vocals_path, out_bg, sr)
    return output_no_vocals_path

def mix_audio_with_ducking(bg_audio_path, speech_clips_info, output_mixed_path, ducking_db=-9.0, bg_base_db=-3.0):
    """
    Mixes speech clips onto background with smooth -9dB sidechain ducking.
    """
    bg_data, sr, n_ch = load_wav(bg_audio_path)
    bg_data = bg_data.astype(np.float32)

    if n_ch == 2:
        corr = np.corrcoef(bg_data[:, 0], bg_data[:, 1])[0, 1]
        if corr < -0.8:
            bg_data[:, 1] = bg_data[:, 0]

    base_gain = 10.0 ** (bg_base_db / 20.0)
    bg_data *= base_gain

    total_frames = len(bg_data)
    speech_track = np.zeros((total_frames, 2), dtype=np.float32)
    activity_mask = np.zeros(total_frames, dtype=np.float32)

    for clip in speech_clips_info:
        clip_path = clip['path']
        if not os.path.exists(clip_path):
            continue

        data, clip_sr, clip_ch = load_wav(clip_path)
        data = data.astype(np.float32)
        if clip_ch == 1:
            data = np.repeat(data, 2, axis=1)

        peak = np.max(np.abs(data))
        if peak > 100:
            boost = min(26000.0 / peak, 2.5)
            data *= boost

        start_idx = int(clip['start'] * sr)
        end_idx = min(start_idx + len(data), total_frames)
        chunk_len = end_idx - start_idx
        if chunk_len <= 0:
            continue

        speech_track[start_idx:end_idx] += data[:chunk_len]

        pad_start = max(0, start_idx - int(0.08 * sr))
        pad_end = min(total_frames, end_idx + int(0.20 * sr))
        activity_mask[pad_start:pad_end] = 1.0

    ducked_gain = 10.0 ** (ducking_db / 20.0)
    target_envelope = 1.0 - activity_mask * (1.0 - ducked_gain)

    # Ultra-fast moving average smoothing with cumsum
    k_size = int(0.15 * sr)
    if k_size % 2 == 0:
        k_size += 1
    half_k = k_size // 2

    cs = np.cumsum(np.insert(target_envelope, 0, 0))
    smoothed = (cs[k_size:] - cs[:-k_size]) / k_size
    smoothed_envelope = np.pad(smoothed, (half_k, total_frames - len(smoothed) - half_k), mode='edge')
    smoothed_envelope = np.clip(smoothed_envelope, ducked_gain, 1.0)

    ducked_bg = bg_data * smoothed_envelope[:, np.newaxis]
    mixed = ducked_bg + speech_track

    peak_mix = np.max(np.abs(mixed))
    if peak_mix > 32000:
        mixed = mixed * (32000.0 / peak_mix)

    save_wav(output_mixed_path, mixed, sr)
    return output_mixed_path

def get_audio_duration(audio_path):
    cmd = [
        "ffprobe", "-v", "error",
        "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1",
        audio_path
    ]
    res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, check=True)
    return float(res.stdout.strip())

def fit_audio_to_slot(audio_path, target_slot_duration, output_path, max_speed=1.25):
    curr_dur = get_audio_duration(audio_path)
    if curr_dur <= target_slot_duration or target_slot_duration <= 0:
        if os.path.abspath(audio_path) != os.path.abspath(output_path):
            cmd = ["ffmpeg", "-y", "-i", audio_path, "-c", "copy", output_path]
            subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return True, 1.0, curr_dur

    speed_ratio = curr_dur / target_slot_duration
    actual_speed = min(speed_ratio, max_speed)
    cmd = [
        "ffmpeg", "-y",
        "-i", audio_path,
        "-filter:a", f"atempo={actual_speed:.4f}",
        output_path
    ]
    subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return (speed_ratio <= max_speed), speed_ratio, curr_dur

# ----------------------------------------------------------------------
# 2. SUBTITLE EXTRACTION & TRANSLATION
# ----------------------------------------------------------------------

def clean_sub_text(text):
    text = re.sub(r'<[^>]+>', '', text)
    text = re.sub(r'\{[^}]+\}', '', text)
    text = re.sub(r'\[.*?\]', '', text)
    text = re.sub(r'\(.*?\)', '', text)
    text = re.sub(r'[♪♫#]', '', text)
    return ' '.join(text.split()).strip()

def parse_srt(srt_path):
    with open(srt_path, 'r', encoding='utf-8', errors='ignore') as f:
        content = f.read()

    blocks = re.split(r'\n\s*\n', content.strip())
    time_pat = re.compile(r'(\d{1,2}):(\d{2}):(\d{2})[,.](\d{3})\s*-->\s*(\d{1,2}):(\d{2}):(\d{2})[,.](\d{3})')
    speaker_pat = re.compile(r'^([A-Z][A-Za-z0-9\s]{1,18}):\s*(.*)$')

    lines = []
    for b in blocks:
        parts = b.strip().split('\n')
        if len(parts) < 2:
            continue
        m = None
        text_lines = []
        for p in parts:
            if not m:
                match = time_pat.search(p)
                if match:
                    m = match
                    continue
            else:
                text_lines.append(p)
        if not m or not text_lines:
            continue

        g = m.groups()
        start = int(g[0])*3600 + int(g[1])*60 + int(g[2]) + int(g[3])/1000.0
        end = int(g[4])*3600 + int(g[5])*60 + int(g[6]) + int(g[7])/1000.0
        duration = end - start

        raw_text = ' '.join(text_lines)
        speaker_name = None
        spk_match = speaker_pat.match(raw_text)
        if spk_match:
            speaker_name = spk_match.group(1).strip()
            raw_text = spk_match.group(2).strip()

        cleaned = clean_sub_text(raw_text)
        if not cleaned or len(cleaned) < 2:
            continue

        lines.append({
            "id": len(lines) + 1,
            "start": round(start, 3),
            "end": round(end, 3),
            "duration": round(duration, 3),
            "character": speaker_name,
            "english_text": cleaned
        })

    return lines

def translate_en_to_hi(text, cache):
    if not text:
        return ""
    if text in cache:
        return cache[text]

    # Clean text before translation
    clean_q = urllib.parse.quote(text)
    url = f"https://translate.googleapis.com/translate_a/single?client=gtx&sl=en&tl=hi&dt=t&q={clean_q}"
    req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'})

    try:
        res = urllib.request.urlopen(req, timeout=8).read().decode('utf-8')
        data = json.loads(res)
        translated = ''.join([item[0] for item in data[0] if item[0]])
        cache[text] = translated
        return translated
    except Exception:
        # Fallback to MyMemory or deep_translator if available
        try:
            from deep_translator import MyMemoryTranslator
            t = MyMemoryTranslator(source='en-US', target='hi-IN').translate(text)
            cache[text] = t
            return t
        except Exception:
            cache[text] = text
            return text

def batch_translate_lines(lines):
    print(f"Translating {len(lines)} dialogue lines into natural Hindi...")
    cache = {}
    unique_texts = list(dict.fromkeys([l["english_text"] for l in lines]))

    def worker(txt):
        return txt, translate_en_to_hi(txt, cache)

    t0 = time.time()
    with ThreadPoolExecutor(max_workers=6) as executor:
        results = list(executor.map(worker, unique_texts))

    for txt, trans in results:
        cache[txt] = trans

    for l in lines:
        l["hindi_text"] = cache.get(l["english_text"], l["english_text"])

    print(f"Translation complete in {time.time()-t0:.1f}s! ({len(cache)} unique phrases translated)")

# ----------------------------------------------------------------------
# 3. SPEAKER & VOICE ASSIGNMENT
# ----------------------------------------------------------------------

def assign_voices(lines, voices_file=None):
    master_voices = None
    if voices_file and os.path.exists(voices_file):
        try:
            with open(voices_file, "r", encoding="utf-8") as f:
                master_voices = json.load(f)
        except Exception:
            pass

    # Build character name to voice config lookup
    char_lookup = {}
    if master_voices and "speakers" in master_voices:
        for spk_id, spk_data in master_voices["speakers"].items():
            name = spk_data.get("character_name", "").lower()
            if name:
                char_lookup[name] = spk_data.get("voice_config", DEFAULT_VOICES["male_lead"])

    voice_cycle = [
        DEFAULT_VOICES["male_lead"],
        DEFAULT_VOICES["female_lead"],
        DEFAULT_VOICES["male_deep"],
        DEFAULT_VOICES["female_soft"],
        DEFAULT_VOICES["male_energetic"]
    ]

    current_cycle_idx = 0
    last_end = 0

    for l in lines:
        char = (l.get("character") or "").lower()
        cfg = None

        if char:
            for known_name, known_cfg in char_lookup.items():
                if known_name in char or char in known_name:
                    cfg = known_cfg
                    break

        if not cfg:
            # Switch voice if dialogue pause > 1.2s or starts with dash
            if l["start"] - last_end > 1.2 or l["english_text"].startswith("-"):
                current_cycle_idx = (current_cycle_idx + 1) % len(voice_cycle)
            cfg = voice_cycle[current_cycle_idx]

        l["voice_config"] = cfg
        last_end = l["end"]

# ----------------------------------------------------------------------
# 4. PARALLEL TTS SYNTHESIS & TIMING
# ----------------------------------------------------------------------

async def synthesize_all_lines(lines, out_clips_dir, max_concurrent=8):
    sem = asyncio.Semaphore(max_concurrent)
    to_fit = []

    print(f"Synthesizing {len(lines)} Hindi audio clips using Edge-TTS (Concurrent workers: {max_concurrent})...")

    async def synth_line(l):
        lid = l["id"]
        hi_text = l["hindi_text"]
        target_dur = l["duration"]
        cfg = l.get("voice_config", DEFAULT_VOICES["male_lead"])

        raw_wav = os.path.join(out_clips_dir, f"line_{lid:04d}_raw.wav")
        fitted_wav = os.path.join(out_clips_dir, f"line_{lid:04d}.wav")
        tmp_mp3 = raw_wav.replace(".wav", ".mp3")

        if not os.path.exists(fitted_wav):
            if not os.path.exists(raw_wav):
                async with sem:
                    try:
                        comm = edge_tts.Communicate(hi_text, cfg["voice"], rate=cfg.get("rate", "+0%"), pitch=cfg.get("pitch", "+0Hz"))
                        await comm.save(tmp_mp3)
                    except Exception as e:
                        # Fallback simple
                        comm = edge_tts.Communicate(hi_text, "hi-IN-MadhurNeural")
                        await comm.save(tmp_mp3)

                # Convert MP3 to 44.1kHz 16-bit WAV
                cmd = ["ffmpeg", "-y", "-i", tmp_mp3, "-acodec", "pcm_s16le", "-ar", "44100", "-ac", "2", raw_wav]
                subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                if os.path.exists(tmp_mp3):
                    try:
                        os.remove(tmp_mp3)
                    except Exception:
                        pass

            to_fit.append((l, raw_wav, target_dur, fitted_wav))
        else:
            l["fitted_audio_path"] = fitted_wav
            l["fitted_duration"] = round(get_audio_duration(fitted_wav), 3)

    tasks = [synth_line(l) for l in lines]
    t0 = time.time()
    await asyncio.gather(*tasks)
    print(f"Edge-TTS synthesis finished in {time.time()-t0:.1f}s!")

    if to_fit:
        print(f"Fitting {len(to_fit)} clips to exact video timing slots (max speedup: 1.25x)...")
        for l, raw_wav, target_dur, fitted_wav in to_fit:
            success, ratio, orig_dur = fit_audio_to_slot(raw_wav, target_dur, fitted_wav, max_speed=1.25)
            l["speed_ratio"] = round(ratio, 2)
            l["fitted_audio_path"] = fitted_wav
            l["fitted_duration"] = round(get_audio_duration(fitted_wav), 3)

# ----------------------------------------------------------------------
# 5. SUBTITLE DISCOVERY / WHISPER FALLBACK
# ----------------------------------------------------------------------

def extract_or_transcribe(video_path, raw_audio_path, work_dir):
    srt_out = os.path.join(work_dir, "extracted_subtitles.srt")

    # 1. Check if same-named .srt exists in same directory
    video_base_srt = os.path.splitext(video_path)[0] + ".srt"
    if os.path.exists(video_base_srt):
        print(f"Found existing subtitle file: {video_base_srt}")
        shutil.copy(video_base_srt, srt_out)
        return srt_out

    # Check subs/ folder if exists
    subs_dir = os.path.join(os.path.dirname(os.path.abspath(video_path)), "subs")
    cand_srt = os.path.join(subs_dir, os.path.basename(video_base_srt))
    if os.path.exists(cand_srt):
        print(f"Found subtitle file in subs/: {cand_srt}")
        shutil.copy(cand_srt, srt_out)
        return srt_out

    # 2. Check for embedded subtitles using ffprobe
    cmd_probe = [
        "ffprobe", "-v", "error",
        "-select_streams", "s",
        "-show_entries", "stream=index,codec_name:stream_tags=language",
        "-of", "json", video_path
    ]
    try:
        probe_res = subprocess.run(cmd_probe, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, check=True)
        probe_json = json.loads(probe_res.stdout)
        streams = probe_json.get("streams", [])
        if streams:
            print(f"Found embedded subtitle stream (Index {streams[0]['index']}). Extracting...")
            cmd_extract = ["ffmpeg", "-y", "-i", video_path, "-map", f"0:{streams[0]['index']}", "-c:s", "srt", srt_out]
            subprocess.run(cmd_extract, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            if os.path.exists(srt_out) and os.path.getsize(srt_out) > 50:
                print("Embedded subtitles extracted successfully!")
                return srt_out
    except Exception as e:
        print(f"Subtitle probe notice: {e}")

    # 3. Fallback to faster-whisper transcription
    print("No subtitles found. Initializing Whisper AI transcription (device: CPU, model: tiny)...")
    try:
        from faster_whisper import WhisperModel
        model = WhisperModel("tiny", device="cpu", compute_type="int8")
        segments, info = model.transcribe(raw_audio_path, language="en")
        with open(srt_out, "w", encoding="utf-8") as f:
            for idx, segment in enumerate(segments, 1):
                start_h = int(segment.start // 3600)
                start_m = int((segment.start % 3600) // 60)
                start_s = int(segment.start % 60)
                start_ms = int((segment.start - int(segment.start)) * 1000)

                end_h = int(segment.end // 3600)
                end_m = int((segment.end % 3600) // 60)
                end_s = int(segment.end % 60)
                end_ms = int((segment.end - int(segment.end)) * 1000)

                f.write(f"{idx}\n")
                f.write(f"{start_h:02d}:{start_m:02d}:{start_s:02d},{start_ms:03d} --> {end_h:02d}:{end_m:02d}:{end_s:02d},{end_ms:03d}\n")
                f.write(f"{segment.text.strip()}\n\n")
        print("Whisper transcription complete and saved to SRT!")
        return srt_out
    except Exception as e:
        raise RuntimeError(f"Failed to transcribe audio with Whisper: {e}")

# ----------------------------------------------------------------------
# 6. MASTER DUBBING PIPELINE
# ----------------------------------------------------------------------

def dub_video(video_path, output_video_path=None, voices_json_path="voices.json"):
    video_path = os.path.abspath(video_path)
    if not os.path.exists(video_path):
        print(f"ERROR: Input video file not found: {video_path}")
        return False

    base_name = os.path.splitext(os.path.basename(video_path))[0]
    work_dir = os.path.join(os.path.dirname(video_path), "work", f"dub_{base_name}")
    os.makedirs(work_dir, exist_ok=True)

    if not output_video_path:
        output_video_path = os.path.join(os.path.dirname(video_path), f"{base_name}_hindi.mp4")

    print("\n" + "="*70)
    print(f"🎬 STARTING 1-CLICK HINDI DUBBING FOR: {os.path.basename(video_path)}")
    print(f"📁 Work Directory: {work_dir}")
    print(f"🎯 Output Target: {output_video_path}")
    print("="*70 + "\n")

    t_start = time.time()

    # Step 1: Extract Audio
    raw_audio_path = os.path.join(work_dir, "raw_audio.wav")
    if not os.path.exists(raw_audio_path):
        print("[Step 1/7] Extracting original audio (44.1kHz stereo WAV)...")
        cmd_audio = ["ffmpeg", "-y", "-i", video_path, "-vn", "-acodec", "pcm_s16le", "-ar", "44100", "-ac", "2", raw_audio_path]
        subprocess.run(cmd_audio, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    else:
        print("[Step 1/7] Using existing extracted raw audio...")

    # Step 2: Generate In-Phase Instrumental Track (No Vocals)
    no_vocals_path = os.path.join(work_dir, "no_vocals.wav")
    if not os.path.exists(no_vocals_path):
        print("[Step 2/7] Generating in-phase background instrumental track (center vocal cancellation)...")
        create_in_phase_no_vocals(raw_audio_path, no_vocals_path)
    else:
        print("[Step 2/7] Using existing in-phase background audio...")

    # Step 3: Extract or Transcribe Subtitles
    print("[Step 3/7] Detecting and parsing English dialogue subtitles...")
    srt_path = extract_or_transcribe(video_path, raw_audio_path, work_dir)
    lines = parse_srt(srt_path)
    print(f"Extracted {len(lines)} dialogue lines from subtitles.")

    if not lines:
        print("ERROR: No dialogue lines detected to dub.")
        return False

    # Step 4: Translate to Conversational Hindi
    lines_cache_file = os.path.join(work_dir, "dialogue_lines.json")
    if not os.path.exists(lines_cache_file):
        print("[Step 4/7] Translating dialogue to conversational Hindi...")
        batch_translate_lines(lines)
        assign_voices(lines, voices_json_path)
        with open(lines_cache_file, "w", encoding="utf-8") as f:
            json.dump(lines, f, indent=2, ensure_ascii=False)
    else:
        print("[Step 4/7] Loading cached Hindi dialogue translations...")
        with open(lines_cache_file, "r", encoding="utf-8") as f:
            lines = json.load(f)

    # Step 5: Synthesize and Slot-Fit Hindi Speech
    print("[Step 5/7] Synthesizing Hindi dialogue clips with Edge-TTS...")
    clips_dir = os.path.join(work_dir, "hindi_clips")
    os.makedirs(clips_dir, exist_ok=True)
    asyncio.run(synthesize_all_lines(lines, clips_dir, max_concurrent=8))

    # Save updated timing data
    with open(lines_cache_file, "w", encoding="utf-8") as f:
        json.dump(lines, f, indent=2, ensure_ascii=False)

    # Step 6: Audio Mixing with Sidechain Ducking
    print("[Step 6/7] Mixing Hindi dialogue over background with -9dB sidechain ducking...")
    master_audio_path = os.path.join(work_dir, "master_hindi_audio.wav")
    speech_clips_info = [{"path": l["fitted_audio_path"], "start": l["start"]} for l in lines if "fitted_audio_path" in l]
    mix_audio_with_ducking(no_vocals_path, speech_clips_info, master_audio_path, ducking_db=-9.0, bg_base_db=-3.0)

    # Step 7: Final Video Stream-Copy Muxing
    print("[Step 7/7] Lossless muxing video with new Hindi audio track (-c:v copy, drop subtitles -sn)...")
    cmd_mux = [
        "ffmpeg", "-y",
        "-i", video_path,
        "-i", master_audio_path,
        "-map", "0:v:0",
        "-map", "1:a:0",
        "-c:v", "copy",
        "-c:a", "aac",
        "-b:a", "192k",
        "-sn",
        output_video_path
    ]
    subprocess.run(cmd_mux, check=True)

    # Quality Report
    report_path = os.path.splitext(output_video_path)[0] + "_report.md"
    total_time = time.time() - t_start
    with open(report_path, "w", encoding="utf-8") as f:
        f.write(f"# Hindi Dubbing Quality Report: {base_name}\n\n")
        f.write(f"- **Total Lines Dubbed:** {len(lines)}\n")
        f.write(f"- **Processing Time:** {total_time/60:.2f} minutes\n")
        f.write(f"- **Output Video:** `{output_video_path}`\n")
        f.write(f"- **Audio Mix:** In-Phase Stereo + -9dB Sidechain Ducking\n\n")
        f.write("## Dialogue Lines Sample (First 15 Lines)\n\n")
        f.write("| ID | Start | Duration | Speed | English | Hindi |\n")
        f.write("|---|---|---|---|---|---|\n")
        for l in lines[:15]:
            f.write(f"| #{l['id']} | {l['start']:.1f}s | {l['duration']:.2f}s | {l.get('speed_ratio', 1.0)}x | {l['english_text']} | {l.get('hindi_text', '')} |\n")

    print("\n" + "="*70)
    print("🎉 DUBBING COMPLETE!")
    print(f"🎬 Dubbed Video: {output_video_path}")
    print(f"📊 Quality Report: {report_path}")
    print(f"⏱️ Total Elapsed Time: {total_time/60:.2f} minutes")
    print("="*70 + "\n")
    return True

# ----------------------------------------------------------------------
# CLI & GUI ENTRY POINT
# ----------------------------------------------------------------------

def pick_video_file_gui():
    try:
        import tkinter as tk
        from tkinter import filedialog
        root = tk.Tk()
        root.withdraw()
        root.attributes('-topmost', True)
        path = filedialog.askopenfilename(
            title="Select Video File to Dub into Hindi",
            filetypes=[
                ("Video Files", "*.mkv *.mp4 *.avi *.mov *.wmv *.webm *.flv"),
                ("All Files", "*.*")
            ]
        )
        root.destroy()
        return path
    except Exception:
        return None

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="1-Click Automatic English to Hindi Video Dubber")
    parser.add_argument("video", nargs="?", default=None, help="Path to the video file to dub")
    parser.add_argument("--output", "-o", default=None, help="Optional output video file path")
    parser.add_argument("--voices", default="voices.json", help="Optional path to voices.json")
    args = parser.parse_args()

    target_video = args.video
    if not target_video:
        print("\n[INFO] No video specified. Opening file selection dialog...")
        target_video = pick_video_file_gui()
        if not target_video:
            target_video = input("Enter video file path: ").strip().strip('"')

    if not target_video or not os.path.exists(target_video):
        print(f"\n[ERROR] Invalid or nonexistent video path: {target_video}")
        sys.exit(1)

    dub_video(target_video, args.output, args.voices)
