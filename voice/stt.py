"""Speech-to-text backends.

Backend priority: faster-whisper -> openai-whisper -> OpenAI API.
"""
from __future__ import annotations
import io
import os
import struct
import tempfile
from pathlib import Path
from typing import List, Optional
from .recorder import SAMPLE_RATE, CHANNELS, BYTES_PER_SAMPLE

_faster_whisper_model = None
_openai_whisper_model = None
DEFAULT_MODEL_SIZE = os.environ.get("NANO_CLAUDE_WHISPER_MODEL", "base")

def _pcm_to_wav(pcm_bytes):
    num_samples = len(pcm_bytes) // BYTES_PER_SAMPLE
    byte_rate = SAMPLE_RATE * CHANNELS * BYTES_PER_SAMPLE
    block_align = CHANNELS * BYTES_PER_SAMPLE
    data_size = len(pcm_bytes)
    header = struct.pack(
        "<4sI4s4sIHHIIHH4sI", b"RIFF", 36 + data_size, b"WAVE", b"fmt ",
        16, 1, CHANNELS, SAMPLE_RATE, byte_rate, block_align, 16, b"data", data_size,
    )
    return header + pcm_bytes

def check_stt_availability():
    try:
        import faster_whisper
        return True, None
    except ImportError:
        pass
    try:
        import whisper
        return True, None
    except ImportError:
        pass
    if os.environ.get("OPENAI_API_KEY"):
        return True, None
    return False, "No STT backend available."

def _has_cuda():
    try:
        import torch
        return torch.cuda.is_available()
    except ImportError:
        pass
    try:
        import ctranslate2
        return "cuda" in ctranslate2.get_supported_compute_types("cuda")
    except Exception:
        return False

def _get_faster_whisper_model():
    global _faster_whisper_model
    if _faster_whisper_model is None:
        from faster_whisper import WhisperModel
        device = "cuda" if _has_cuda() else "cpu"
        compute = "float16" if device == "cuda" else "int8"
        _faster_whisper_model = WhisperModel(DEFAULT_MODEL_SIZE, device=device, compute_type=compute)
    return _faster_whisper_model

def _keyterms_to_prompt(keyterms):
    if not keyterms:
        return ""
    return ", ".join(keyterms[:40])

def _transcribe_faster_whisper(pcm_bytes, keyterms, language):
    import numpy as np
    model = _get_faster_whisper_model()
    audio = np.frombuffer(pcm_bytes, dtype=np.int16).astype(np.float32) / 32768.0
    initial_prompt = _keyterms_to_prompt(keyterms)
    lang = None if not language or language == "auto" else language
    segments, _info = model.transcribe(audio, language=lang, initial_prompt=initial_prompt,
                                        vad_filter=True, vad_parameters=dict(min_silence_duration_ms=300))
    return " ".join(seg.text for seg in segments).strip()

def _get_openai_whisper_model():
    global _openai_whisper_model
    if _openai_whisper_model is None:
        import whisper
        _openai_whisper_model = whisper.load_model(DEFAULT_MODEL_SIZE)
    return _openai_whisper_model

def _transcribe_openai_whisper(pcm_bytes, keyterms, language):
    import numpy as np
    model = _get_openai_whisper_model()
    audio = np.frombuffer(pcm_bytes, dtype=np.int16).astype(np.float32) / 32768.0
    initial_prompt = _keyterms_to_prompt(keyterms)
    options = {"initial_prompt": initial_prompt} if initial_prompt else {}
    if language and language != "auto":
        options["language"] = language
    result = model.transcribe(audio, **options)
    return result.get("text", "").strip()

def _transcribe_openai_api(pcm_bytes, language):
    from openai import OpenAI
    client = OpenAI()
    wav = _pcm_to_wav(pcm_bytes)
    kwargs = {"model": "whisper-1", "file": ("audio.wav", io.BytesIO(wav), "audio/wav")}
    if language and language != "auto":
        kwargs["language"] = language
    transcript = client.audio.transcriptions.create(**kwargs)
    return transcript.text.strip()

def transcribe(pcm_bytes, keyterms=None, language="auto"):
    if not pcm_bytes:
        return ""
    terms = keyterms or []
    lang = None if language == "auto" else language
    try:
        import faster_whisper
        return _transcribe_faster_whisper(pcm_bytes, terms, lang)
    except ImportError:
        pass
    try:
        import whisper
        return _transcribe_openai_whisper(pcm_bytes, terms, lang)
    except ImportError:
        pass
    if os.environ.get("OPENAI_API_KEY"):
        return _transcribe_openai_api(pcm_bytes, lang)
    raise RuntimeError("No STT backend available.")
