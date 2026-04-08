"""Voice package for nano-claude-code."""
from .recorder import check_recording_availability, record_until_silence
from .stt import check_stt_availability, transcribe
from .keyterms import get_voice_keyterms

def check_voice_deps():
    rec_ok, rec_reason = check_recording_availability()
    if not rec_ok:
        return False, rec_reason
    stt_ok, stt_reason = check_stt_availability()
    if not stt_ok:
        return False, stt_reason
    return True, None

def voice_input(language="auto", max_seconds=30, on_energy=None):
    keyterms = get_voice_keyterms()
    pcm = record_until_silence(max_seconds=max_seconds, on_energy=on_energy)
    if not pcm:
        return ""
    return transcribe(pcm, keyterms=keyterms, language=language)

__all__ = [
    "check_voice_deps", "check_recording_availability",
    "check_stt_availability", "record_until_silence",
    "transcribe", "get_voice_keyterms", "voice_input",
]
