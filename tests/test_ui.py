from collections import deque
import os
import queue
import time
import tkinter as tk
import unittest
from pitchscope.audio import Device
from pitchscope.app import PitchScope
from pitchscope.dsp import Pitch

class FakeEngine:
    def __init__(self):
        self.events = queue.Queue()
        self.results = deque(maxlen=1)
        self.commands = []
    def request(self, command, **data):
        self.commands.append((command, data))

class UiTests(unittest.TestCase):
    def test_modes_readout_and_stop(self):
        engine = FakeEngine()
        try:
            app = PitchScope(engine)
        except tk.TclError:
            if os.environ.get('GITHUB_ACTIONS'):
                raise
            self.skipTest('No working Tcl/Tk runtime')
        try:
            app.update()
            engine.events.put(('devices', [Device(0, 'Test speakers', 'system', 48000, 2, True), Device(1, 'Test mic', 'mic', 48000, 1, True)]))
            app._poll()
            app.start()
            self.assertTrue(app.running)
            app.mode.set('mic')
            app.change_mode()
            self.assertTrue(app.running)
            self.assertEqual(engine.commands[-1][1]['device'].mode, 'mic')
            engine.results.append((app.generation, time.monotonic(), Pitch(440, .99, -20), -20))
            app._poll()
            app.update()
            self.assertEqual(app.note.get(), 'A4')
            self.assertEqual(len(app.records), 1)
            self.assertLessEqual(app.status_label.winfo_rooty() + app.status_label.winfo_height(), app.winfo_rooty() + app.winfo_height())
            app.stop()
            self.assertEqual(app.note.get(), '—')
            self.assertEqual(len(app.records), 1)
            app.start()
            engine.results.append((app.generation - 1, time.monotonic(), Pitch(880, .99, -20), -20))
            app._poll()
            self.assertEqual(app.note.get(), '—')
        finally:
            app.destroy()
