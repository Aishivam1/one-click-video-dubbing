import os
import subprocess
import json

def get_audio_duration(audio_path):
    """
    Returns audio duration in seconds using ffprobe.
    """
    if not os.path.exists(audio_path):
        raise FileNotFoundError(f"Audio file does not exist: {audio_path}")
        
    cmd = [
        "ffprobe", "-v", "error",
        "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1",
        audio_path
    ]
    res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, check=True)
    return float(res.stdout.strip())

def fit_audio_to_slot(audio_path, target_slot_duration, output_path, max_speed=1.25):
    """
    Adjusts audio duration to fit within target_slot_duration.
    - If current duration <= target_slot_duration: copies as-is.
    - If current duration > target_slot_duration:
      - If speedup needed is <= max_speed (e.g. 1.25x): applies ffmpeg atempo.
      - If speedup needed > max_speed: caps at max_speed (1.25x), generates audio,
        and returns (False, speed_ratio, curr_dur) so quality report flags it for re-translation.
    """
    curr_dur = get_audio_duration(audio_path)
    
    if curr_dur <= target_slot_duration or target_slot_duration <= 0:
        if os.path.abspath(audio_path) != os.path.abspath(output_path):
            cmd = ["ffmpeg", "-y", "-i", audio_path, "-c", "copy", output_path]
            subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return True, 1.0, curr_dur
        
    speed_ratio = curr_dur / target_slot_duration
    
    if speed_ratio <= max_speed:
        cmd = [
            "ffmpeg", "-y",
            "-i", audio_path,
            "-filter:a", f"atempo={speed_ratio:.4f}",
            output_path
        ]
        subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return True, speed_ratio, curr_dur
    else:
        # Exceeds max speed. Cap at max_speed (1.25x) so audio is created, but flag False
        cmd = [
            "ffmpeg", "-y",
            "-i", audio_path,
            "-filter:a", f"atempo={max_speed:.4f}",
            output_path
        ]
        subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return False, speed_ratio, curr_dur

if __name__ == "__main__":
    print("timing_fitter module ready.")
