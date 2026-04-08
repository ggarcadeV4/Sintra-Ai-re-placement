"""Audio capture for voice input.

Backend priority: sounddevice -> arecord -> sox rec.
All backends capture raw PCM: 16 kHz, 16-bit signed LE, mono.
"""
from __future__ import annotations
import io
import shutil
import subprocess
import threading
from pathlib import Path

SAMPLE_RATE = 16000
CHANNELS = 1
DTYPE = "int16"
BYTES_PER_SAMPLE = 2
SILENCE_THRESHOLD_RMS = 0.012
SILENCE_DURATION_SECS = 1.8
CHUNK_SECS = 0.08

def _has_cmd(cmd):
    return shutil.which(cmd) is not None

def check_recording_availability():
    try:
        import sounddevice
        return True, None
    except (ImportError, OSError):
        pass
    if _has_cmd("arecord"):
        return True, None
    if _has_cmd("rec"):
        return True, None
    return False, "No audio recording backend found."

def _record_sounddevice(max_seconds=30, on_energy=None):
    import sounddevice as sd
    import numpy as np
    chunk_samples = int(SAMPLE_RATE * CHUNK_SECS)
    silence_chunks_needed = int(SILENCE_DURATION_SECS / CHUNK_SECS)
    max_chunks = int(max_seconds / CHUNK_SECS)
    chunks = []
    silence_count = 0
    done_evt = threading.Event()

    def callback(indata, frames, time_info, status):
        nonlocal silence_count
        mono = indata[:, 0].copy()
        chunks.append(mono.tobytes())
        rms = float(np.sqrt(np.mean(mono.astype(np.float32) ** 2))) / 32768.0
        if on_energy:
            on_energy(rms)
        if rms < SILENCE_THRESHOLD_RMS:
            silence_count += 1
        else:
            silence_count = 0
        has_speech = len(chunks) >= 3
        if has_speech and silence_count >= silence_chunks_needed:
            done_evt.set()
            raise sd.CallbackStop()
        if len(chunks) >= max_chunks:
            done_evt.set()
            raise sd.CallbackStop()

    with sd.InputStream(samplerate=SAMPLE_RATE, channels=CHANNELS, dtype=DTYPE,
                        blocksize=chunk_samples, callback=callback):
        done_evt.wait(timeout=max_seconds + 2)
    return b"".join(chunks)

def _record_arecord(max_seconds=30, on_energy=None):
    import numpy as np
    cmd = ["arecord", "-f", "S16_LE", "-r", str(SAMPLE_RATE), "-c", str(CHANNELS),
           "-t", "raw", "-q", "-d", str(max_seconds), "-"]
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
    chunk_bytes = int(SAMPLE_RATE * CHUNK_SECS) * BYTES_PER_SAMPLE
    silence_chunks_needed = int(SILENCE_DURATION_SECS / CHUNK_SECS)
    chunks = []
    silence_count = 0
    try:
        while True:
            raw = proc.stdout.read(chunk_bytes)
            if not raw:
                break
            chunks.append(raw)
            arr = np.frombuffer(raw, dtype=np.int16).astype(np.float32)
            rms = float(np.sqrt(np.mean(arr ** 2))) / 32768.0
            if on_energy:
                on_energy(rms)
            if rms < SILENCE_THRESHOLD_RMS:
                silence_count += 1
            else:
                silence_count = 0
            if len(chunks) >= 3 and silence_count >= silence_chunks_needed:
                break
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=2)
        except subprocess.TimeoutExpired:
            proc.kill()
    return b"".join(chunks)

def _record_sox(max_seconds=30, on_energy=None):
    cmd = ["rec", "-q", "--buffer", "1024", "-t", "raw", "-r", str(SAMPLE_RATE),
           "-e", "signed", "-b", "16", "-c", str(CHANNELS), "-",
           "silence", "1", "0.1", "3%", "1", str(SILENCE_DURATION_SECS), "3%"]
    try:
        result = subprocess.run(cmd, capture_output=True, timeout=max_seconds)
        return result.stdout
    except subprocess.TimeoutExpired as e:
        return e.stdout or b""

def record_until_silence(max_seconds=30, on_energy=None):
    try:
        import sounddevice
        return _record_sounddevice(max_seconds=max_seconds, on_energy=on_energy)
    except (ImportError, OSError):
        pass
    if _has_cmd("arecord"):
        try:
            import numpy
            return _record_arecord(max_seconds=max_seconds, on_energy=on_energy)
        except ImportError:
            return _record_arecord(max_seconds=max_seconds, on_energy=None)
    if _has_cmd("rec"):
        return _record_sox(max_seconds=max_seconds, on_energy=on_energy)
    raise RuntimeError("No audio recording backend found.")
