import os
import subprocess

def export_dubbed_video(original_video_path, mixed_audio_path, output_video_path):
    """
    Exports final video:
    - Copies original video stream (-c:v copy)
    - Adds new Hindi audio track (-c:a aac -b:a 192k)
    - Drops all subtitle streams (-sn)
    """
    cmd = [
        "ffmpeg", "-y",
        "-i", original_video_path,
        "-i", mixed_audio_path,
        "-map", "0:v:0",
        "-map", "1:a:0",
        "-c:v", "copy",
        "-c:a", "aac",
        "-b:a", "192k",
        "-sn",
        output_video_path
    ]
    print(f"Exporting dubbed video to: {output_video_path}")
    subprocess.run(cmd, check=True)
    print("Export completed successfully!")
    return output_video_path

if __name__ == "__main__":
    print("export_video module ready.")

