# 1-Click English to Hindi Video Dubber Guide

Convert **any English video** (TV show, movie, anime, documentary, or YouTube video) into **high-quality Hindi dubbed video** with a **single click**.

---

## ⚡ 3 Ways to Convert

### Option 1: 1-Click Drag & Drop (Recommended)
1. Open Windows File Explorer and find your video (`.mkv`, `.mp4`, `.avi`, `.webm`, etc.).
2. **Drag the video file and drop it right onto `one_click_dub.bat`**.
3. That's it! A command window will open, show real-time progress, and export `[video_name]_hindi.mp4` when finished.

### Option 2: Double-Click File Picker
1. Double-click `one_click_dub.bat`.
2. A Windows file selection dialog will pop up.
3. Browse and select your video file, then click **Open**.

### Option 3: Command-Line (For advanced users)
Open PowerShell in `D:\episode` and run:
```powershell
python auto_dubber.py "D:\episode\Flash.S02E03.mkv"
```

### Option 4: Batch Dub an Entire Season / Folder
To convert all episodes in a folder automatically:
- Drag the folder containing your videos onto `dub_folder.bat` (or double-click it inside the folder).
- It will process every video file one by one!

---

## ⚙️ What Happens Automatically (Under the Hood)

1. **Audio Extraction:**
   - FFmpeg extracts clean 44.1kHz 16-bit stereo PCM audio (`raw_audio.wav`).
2. **In-Phase Instrumental Track:**
   - NumPy runs center-channel vocal cancellation `0.5 * (Left - Right)` and duplicates to stereo.
   - **Zero phase cancellation** on mobile/laptop speakers while 100% preserving background music, Foley, and action SFX.
3. **Dialogue Subtitle Extraction:**
   - Checks for existing `.srt` file.
   - If not found, automatically extracts embedded subtitles from the video container with FFmpeg.
   - If no subtitles exist at all, automatically transcribes the audio using **Whisper AI** (`faster-whisper`).
4. **Natural Conversational Hindi Translation:**
   - Subtitle cues are cleaned of HTML tags and sound effects (`[music]`, `(screams)`).
   - High-speed concurrent translation into natural, idiomatic Hindi.
5. **Character Voice Assignment:**
   - Matches character names from `voices.json` (Barry Allen, Joe West, Caitlin Snow, Cisco Ramon, etc.).
   - For other videos/characters, dynamically rotates between expressive male and female voices.
6. **Parallel Microsoft Edge-TTS Synthesis:**
   - Uses 8 concurrent async workers.
   - Synthesizes 600+ dialogue lines in under 60-80 seconds.
7. **Precision Slot-Fitting (Max 1.25x Speed Cap):**
   - Fits each speech clip to its video timestamp slot.
   - Speedups are strictly capped at `1.25x` using FFmpeg `atempo` filter to ensure voices never sound cartoonish or rushed.
8. **Sidechain Ducking Audio Mix:**
   - Dialogue placed at full, crisp volume (-2 dBFS).
   - Smooth `-9 dB` sidechain ducking attenuates background music during dialogue and rises during silence.
9. **Lossless Stream-Copy Muxing:**
   - Original video stream is copied losslessly (`-c:v copy`).
   - Old English subtitle tracks are removed (`-sn`).
   - Dubbed master audio is muxed as high-bitrate AAC (`-c:a aac -b:a 192k`).
   - Dubbed video is saved as `[filename]_hindi.mp4`.
10. **Quality Report:**
    - Generates `[filename]_report.md` detailing dialogue count, timing metrics, and lines.

---

## 📁 Key Files Reference

| File | Purpose |
|---|---|
| `one_click_dub.bat` | The 1-click Windows drag-and-drop / double-click launcher |
| `dub_folder.bat` | Batch launcher to dub all videos in a folder in one go |
| `auto_dubber.py` | The master automation Python engine |
| `voices.json` | Master character voice registry (editable for custom voices) |
| `Flash.S02E01_hindi.mp4` | Episode 1 completed Hindi dubbed video (42 min) |
| `Flash.S02E02_hindi.mp4` | Episode 2 completed Hindi dubbed video (42 min) |
