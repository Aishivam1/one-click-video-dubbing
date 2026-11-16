import os
import wave
import json
import numpy as np

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
    Creates an in-phase background instrumental track by canceling center-panned vocals.
    Ensures Left and Right channels have identical phase so there is ZERO phase cancellation
    on laptop speakers or mono playback.
    """
    raw_data, sr, n_ch = load_wav(raw_audio_path)
    if n_ch < 2:
        # Mono cannot do stereo center cancellation, keep as is
        diff = raw_data.astype(np.float32) * 0.4
        out_bg = np.repeat(diff, 2, axis=1)
    else:
        # Center channel cancellation: (L - R) / 2
        # Apply to BOTH channels in-phase!
        diff = 0.5 * (raw_data[:, 0].astype(np.float32) - raw_data[:, 1].astype(np.float32))
        out_bg = np.stack([diff, diff], axis=1)
        
    save_wav(output_no_vocals_path, out_bg, sr)
    return output_no_vocals_path

def mix_audio_with_ducking(bg_audio_path, speech_clips_info, output_mixed_path, ducking_db=-9.0, bg_base_db=-3.0):
    """
    High-fidelity Python audio mixer with automated smooth sidechain ducking.
    - Places each speech clip at its exact start timestamp at full, clear volume.
    - Ensures background audio is in-phase (no acoustic phase cancellation).
    - Smoothly attenuates background music during dialogue with 50ms attack & 250ms release.
    """
    if not os.path.exists(bg_audio_path):
        raise FileNotFoundError(f"Background audio file not found: {bg_audio_path}")

    bg_data, sr, n_ch = load_wav(bg_audio_path)
    bg_data = bg_data.astype(np.float32)
    
    # Ensure background is in-phase stereo
    if n_ch == 2:
        # Check if L and R are inverted (-1 correlation)
        corr = np.corrcoef(bg_data[:, 0], bg_data[:, 1])[0, 1]
        if corr < -0.8:
            # Fix phase inversion! Make R in phase with L
            bg_data[:, 1] = bg_data[:, 0]
            
    # Apply slight baseline attenuation to background so dialogue sits nicely in the mix
    base_gain = 10.0 ** (bg_base_db / 20.0) # -3 dB = 0.707
    bg_data *= base_gain
    
    total_frames = len(bg_data)
    speech_track = np.zeros((total_frames, 2), dtype=np.float32)
    activity_mask = np.zeros(total_frames, dtype=np.float32)
    
    print(f"Mixing {len(speech_clips_info)} speech clips over {total_frames/sr:.2f}s background...")
    
    for clip in speech_clips_info:
        clip_path = clip['path']
        if not os.path.exists(clip_path):
            continue
            
        data, clip_sr, clip_ch = load_wav(clip_path)
        data = data.astype(np.float32)
        if clip_ch == 1:
            data = np.repeat(data, 2, axis=1)
            
        # Target speech peak level ~ 26,000 (-2 dBFS)
        peak = np.max(np.abs(data))
        if peak > 100:
            boost = min(26000.0 / peak, 2.5) # boost up to 2.5x if speech was quiet
            data *= boost
            
        start_idx = int(clip['start'] * sr)
        end_idx = min(start_idx + len(data), total_frames)
        chunk_len = end_idx - start_idx
        if chunk_len <= 0:
            continue
            
        speech_track[start_idx:end_idx] += data[:chunk_len]
        
        # Mark active dialogue region with padding for smooth ducking
        pad_start = max(0, start_idx - int(0.08 * sr))
        pad_end = min(total_frames, end_idx + int(0.20 * sr))
        activity_mask[pad_start:pad_end] = 1.0

    # Build smooth ducking curve
    # Normal bg = 1.0; Ducked bg = 10^(ducking_db / 20) (e.g. -9 dB = 0.355)
    ducked_gain = 10.0 ** (ducking_db / 20.0)
    target_envelope = 1.0 - activity_mask * (1.0 - ducked_gain)
    
    # Smooth the envelope with a 150ms moving average window
    kernel_size = int(0.15 * sr)
    if kernel_size % 2 == 0:
        kernel_size += 1
    kernel = np.ones(kernel_size) / kernel_size
    smoothed_envelope = np.convolve(target_envelope, kernel, mode='same')
    smoothed_envelope = np.clip(smoothed_envelope, ducked_gain, 1.0)
    
    # Apply ducking to background
    ducked_bg = bg_data * smoothed_envelope[:, np.newaxis]
    
    # Mix speech and ducked background
    mixed = ducked_bg + speech_track
    
    # Peak limiter: if sum exceeds 32000, smoothly scale back
    peak_mix = np.max(np.abs(mixed))
    if peak_mix > 32000:
        mixed = mixed * (32000.0 / peak_mix)
        
    save_wav(output_mixed_path, mixed, sr)
    print(f"Mix complete! Master audio saved to: {output_mixed_path} (Speech peak: {np.max(np.abs(speech_track)):.0f}, Master peak: {np.max(np.abs(mixed)):.0f})")
    return output_mixed_path

if __name__ == "__main__":
    print("audio_mixer module loaded.")
