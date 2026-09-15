"""FFT-accelerated YIN fundamental frequency estimation (no audio I/O)."""
from dataclasses import dataclass
import math

import numpy as np


@dataclass(frozen=True)
class Pitch:
    frequency: float
    confidence: float
    dbfs: float


def detect_pitch(samples, sample_rate, gate_db=-55.0, fmin=50.0, fmax=2000.0):
    """Estimate one fundamental; return None for silence or aperiodic audio.

    A fixed comparison window avoids the shrinking-window bias of naive
    autocorrelation. The first sufficiently deep YIN trough suppresses octave
    errors. Input is normalized float PCM; no window function is applied.
    """
    x = np.asarray(samples, dtype=np.float64)
    if x.ndim != 1 or len(x) < 32 or not np.all(np.isfinite(x)):
        return None
    if not (sample_rate > 0 and 0 < fmin < fmax < sample_rate / 2):
        raise ValueError("Invalid sample rate or frequency range")
    x = x - np.mean(x)
    rms = float(np.sqrt(np.mean(x * x)))
    dbfs = 20.0 * math.log10(max(rms, 1e-12))
    if dbfs < gate_db:
        return None
    width = len(x) // 2
    lo = max(2, int(sample_rate / fmax))
    hi = min(width - 2, int(math.ceil(sample_rate / fmin)))
    if hi <= lo:
        return None
    fft_size = 1 << (len(x) + width - 1).bit_length()
    correlation = np.fft.irfft(
        np.fft.rfft(x, fft_size) * np.conj(np.fft.rfft(x[:width], fft_size)),
        fft_size,
    )[:hi + 2]
    squares = np.concatenate(([0.0], np.cumsum(x * x)))
    lags = np.arange(hi + 2)
    difference = np.maximum(0, squares[width] + squares[lags + width] - squares[lags] - 2 * correlation)
    cmnd = np.ones(hi + 2)
    cmnd[1:] = difference[1:] * np.arange(1, hi + 2) / np.maximum(np.cumsum(difference[1:]), 1e-20)
    lag = lo
    while lag <= hi:
        if cmnd[lag] < 0.15:
            while lag < hi and cmnd[lag + 1] < cmnd[lag]:
                lag += 1
            break
        lag += 1
    if lag > hi:
        return None
    a, b, c = cmnd[lag - 1:lag + 2]
    denom = a - 2 * b + c
    offset = float(np.clip(0.5 * (a - c) / denom, -1, 1)) if abs(denom) > 1e-12 else 0.0
    frequency = float(sample_rate / (lag + offset))
    if not fmin <= frequency <= fmax:
        return None
    return Pitch(frequency, float(np.clip(1 - b, 0, 1)), dbfs)


def note_details(frequency, reference=440.0):
    """Return name, cents, nearest MIDI integer, and continuous MIDI pitch."""
    if not math.isfinite(frequency) or frequency <= 0 or not 400 <= reference <= 480:
        raise ValueError("Invalid frequency or reference")
    midi = 69 + 12 * math.log2(frequency / reference)
    nearest = int(math.floor(midi + 0.5))
    names = ("C", "C♯", "D", "D♯", "E", "F", "F♯", "G", "G♯", "A", "A♯", "B")
    return f"{names[nearest % 12]}{nearest // 12 - 1}", (midi - nearest) * 100, nearest, midi


def strongest_channel(interleaved, channels):
    """Avoid cancellation when a stereo signal has opposite-polarity channels."""
    frames = np.asarray(interleaved).reshape(-1, channels)
    index = int(np.argmax(np.mean(frames.astype(np.float64) ** 2, axis=0)))
    return frames[:, index].copy()
