import math
import unittest
import numpy as np
from pitchscope.dsp import detect_pitch, note_details, strongest_channel

class PitchTests(unittest.TestCase):
    def signal(self, frequency, rate=48000, harmonic=False):
        n = 1 << math.ceil(math.log2(rate * 0.085))
        t = np.arange(n) / rate
        x = 0.3 * np.sin(2 * np.pi * frequency * t + 0.4)
        if harmonic:
            x += 0.45 * np.sin(2 * np.pi * frequency * 2 * t)
            x += 0.15 * np.sin(2 * np.pi * frequency * 3 * t)
        return x

    def test_range_and_rates(self):
        for rate in [44100, 48000, 96000, 192000]:
            for frequency in [55, 65.406, 82.407, 110, 220, 261.626, 440, 880, 1567.982, 1975.533]:
                with self.subTest(rate=rate, frequency=frequency):
                    result = detect_pitch(self.signal(frequency, rate), rate)
                    self.assertIsNotNone(result)
                    self.assertLess(abs(1200 * math.log2(result.frequency / frequency)), 6)

    def test_harmonics(self):
        for frequency in [82.407, 110, 220, 440, 880]:
            result = detect_pitch(self.signal(frequency, harmonic=True), 48000)
            self.assertIsNotNone(result)
            self.assertLess(abs(1200 * math.log2(result.frequency / frequency)), 6)

    def test_invalid_and_noise(self):
        rng = np.random.default_rng(2026)
        for x in [np.zeros(4096), np.ones(4096), rng.normal(0, 0.2, 4096), [np.nan]*4096, [np.inf]*4096, [], np.zeros((4,4))]:
            self.assertIsNone(detect_pitch(x, 48000))

    def test_gate_dc_and_stereo(self):
        wave = self.signal(440)
        self.assertIsNone(detect_pitch(wave * 0.0001, 48000))
        self.assertAlmostEqual(detect_pitch(wave + 0.5, 48000).frequency, 440, delta=0.5)
        mono = strongest_channel(np.column_stack((wave, -wave)).reshape(-1), 2)
        self.assertAlmostEqual(detect_pitch(mono, 48000).frequency, 440, delta=0.5)

    def test_notes_and_cents(self):
        self.assertEqual(note_details(440)[0], 'A4')
        self.assertEqual(note_details(261.625565)[0], 'C4')
        self.assertEqual(note_details(432, 432)[0], 'A4')
        self.assertAlmostEqual(note_details(440*2**(17/1200))[1], 17, places=6)
        self.assertAlmostEqual(note_details(440*2**(-23/1200))[1], -23, places=6)
        for f in [0, -1, float('inf')]:
            with self.assertRaises(ValueError):
                note_details(f)
