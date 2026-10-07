"""Small amplitude envelope for the local avatar; no phoneme claims."""
import array
import math
import sys
import wave

INTERVAL = 0.08

def envelope(path):
    try:
        with wave.open(str(path), 'rb') as audio:
            if audio.getsampwidth() != 2:
                return []
            size = max(1, round(audio.getframerate() * INTERVAL))
            levels = []
            while True:
                chunk = audio.readframes(size)
                if not chunk:
                    break
                samples = array.array('h', chunk)
                if sys.byteorder != 'little':
                    samples.byteswap()
                levels.append(math.sqrt(sum(float(s)*s for s in samples) / len(samples)) / 32768)
        peak = max(levels, default=0)
        return [round(min(1, max(0, (v-0.006) / max(0.04, peak*0.65))), 3) for v in levels]
    except (OSError, EOFError, wave.Error):
        return []
