import os
import json

def format_timestamp(seconds):
    mins = int(seconds // 60)
    secs = int(seconds % 60)
    millis = int((seconds - int(seconds)) * 1000)
    return f"{mins:02d}:{secs:02d}.{millis:03d}"

def generate_quality_report(episode_name, lines_data, voices_data, output_md_path):
    """
    Generates a markdown report summarizing:
    - Lines that needed shortening or heavy speed-up (> 1.15x).
    - Lines with low speaker or gender confidence.
    - Lines with strong emotion (shouting, crying, angry, scared).
    - Exact timestamps for jumping straight to the scene.
    """
    sped_up_lines = []
    low_confidence_speakers = []
    emotional_lines = []
    
    # Check voices
    speakers = voices_data.get("speakers", {})
    for spk_id, spk_info in speakers.items():
        if spk_info.get("pitch_confidence") == "low" or spk_info.get("flag_for_review"):
            low_confidence_speakers.append({
                "speaker_id": spk_id,
                "character": spk_info.get("character_name", "Unknown"),
                "pitch_hz": spk_info.get("detected_median_pitch_hz", "N/A"),
                "assigned_gender": spk_info.get("gender", "unknown")
            })
            
    for line in lines_data:
        speed_ratio = line.get("speed_ratio", 1.0)
        was_shortened = line.get("was_shortened", False)
        emotion = line.get("emotion", "neutral")
        
        if speed_ratio > 1.12 or was_shortened:
            sped_up_lines.append(line)
            
        if emotion in ["shouting", "angry", "scared", "sad", "whisper"]:
            emotional_lines.append(line)
            
    lines_md = [
        f"# Dubbing Quality Report: {episode_name}",
        "",
        "## Summary Overview",
        f"- **Total Dialogue Lines Processed:** {len(lines_data)}",
        f"- **Lines Requiring Timing Speed-up / Shortening:** {len(sped_up_lines)}",
        f"- **Speakers Flagged for Gender/Voice Review:** {len(low_confidence_speakers)}",
        f"- **Lines with High / Nuanced Emotion:** {len(emotional_lines)}",
        "",
        "---",
        "",
        "## 1. Lines Needing Shortening or Speed-up",
        "These lines exceeded the natural slot duration and were adjusted via ffmpeg atempo (max 1.25x) or concise re-translation:",
        ""
    ]
    
    if not sped_up_lines:
        lines_md.append("_None - all lines fit cleanly within their time slots._\n")
    else:
        lines_md.append("| Line ID | Timestamp | Original Duration | Speedup / Status | English Line | Hindi Dubbed Line |")
        lines_md.append("| :--- | :--- | :--- | :--- | :--- | :--- |")
        for l in sped_up_lines:
            ts = f"{format_timestamp(l['start'])} - {format_timestamp(l['end'])}"
            speed_str = f"{l.get('speed_ratio', 1.0):.2f}x" + (" (Shortened)" if l.get("was_shortened") else "")
            lines_md.append(f"| #{l['id']} | `{ts}` | {l['duration']:.2f}s | **{speed_str}** | {l.get('english_text', '')} | {l.get('hindi_text', '')} |")
        lines_md.append("")
        
    lines_md.extend([
        "---",
        "",
        "## 2. Speaker & Gender Confidence Review",
        "Review any speaker where pitch measurement fell in the ambiguous range (155-175 Hz) or voiced sample was short:",
        ""
    ])
    
    if not low_confidence_speakers:
        lines_md.append("_All speakers had clear pitch separation (>95% confidence). No manual intervention needed._\n")
    else:
        lines_md.append("| Speaker ID | Character Name | Median Pitch (Hz) | Assigned Gender | Status |")
        lines_md.append("| :--- | :--- | :--- | :--- | :--- |")
        for spk in low_confidence_speakers:
            lines_md.append(f"| {spk['speaker_id']} | {spk['character']} | {spk['pitch_hz']} Hz | {spk['assigned_gender']} | **Needs Confirmation** |")
        lines_md.append("")
        
    lines_md.extend([
        "---",
        "",
        "## 3. Strong Emotion Lines (Recommended to Listen & Review)",
        "Lines with intense acoustic energy (shouting, heavy grief, whispering, or fear) that may benefit from tone auditioning:",
        "",
        "| Line ID | Timestamp | Speaker | Emotion Tag | English Original | Hindi Translation | Action |",
        "| :--- | :--- | :--- | :--- | :--- | :--- | :--- |"
    ])
    
    for l in emotional_lines:
        ts = f"{format_timestamp(l['start'])} - {format_timestamp(l['end'])}"
        lines_md.append(f"| #{l['id']} | `{ts}` | **{l.get('speaker', 'S?')}** ({l.get('character', '')}) | `{l.get('emotion', '')}` | {l.get('english_text', '')} | {l.get('hindi_text', '')} | [Listen & Verify] |")
        
    lines_md.extend([
        "",
        "---",
        "Generated automatically by the Hindi Dubbing Pipeline."
    ])
    
    with open(output_md_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines_md))
        
    print(f"Quality report written to: {output_md_path}")
    return output_md_path

if __name__ == "__main__":
    print("generate_report module ready.")

