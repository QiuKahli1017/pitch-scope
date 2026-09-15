"""Single-owner audio worker. Tk never touches a PortAudio stream."""
from collections import deque
from dataclasses import dataclass
import math
import queue
import threading
import time

import numpy as np

from .dsp import detect_pitch, strongest_channel


@dataclass(frozen=True)
class Device:
    index: int
    name: str
    mode: str
    rate: int
    channels: int
    default: bool = False


class AudioEngine:
    def __init__(self):
        self.commands = queue.Queue()
        self.events = queue.Queue()
        self.results = deque(maxlen=1)
        self.thread = threading.Thread(target=self._run, daemon=True, name="PitchScope audio")
        self.thread.start()

    def request(self, command, **data):
        self.commands.put((command, data))

    def _run(self):
        try:
            import pyaudiowpatch as pa
            audio = pa.PyAudio()
        except Exception as exc:
            self.events.put(("error", f"音频引擎无法初始化：{exc}"))
            return
        stream = None
        chunks = queue.Queue(maxsize=4)
        ring = np.zeros(4096, dtype=np.float32)
        filled = 0
        generation = 0

        def close_stream():
            nonlocal stream, filled
            if stream is not None:
                try:
                    stream.stop_stream()
                finally:
                    stream.close()
                    stream = None
            filled = 0
            self.results.clear()
            while not chunks.empty():
                try:
                    chunks.get_nowait()
                except queue.Empty:
                    break

        def callback(in_data, frame_count, time_info, status):
            try:
                chunks.put_nowait(in_data)
            except queue.Full:
                pass
            return (None, pa.paContinue)

        def devices():
            wasapi = audio.get_host_api_info_by_type(pa.paWASAPI)
            try:
                default_loop = audio.get_default_wasapi_loopback()["index"]
            except (OSError, LookupError):
                default_loop = -1
            result = []
            for i in range(audio.get_device_count()):
                info = audio.get_device_info_by_index(i)
                if info["hostApi"] != wasapi["index"] or info["maxInputChannels"] < 1:
                    continue
                loopback = bool(info.get("isLoopbackDevice", False))
                result.append(Device(i, info["name"], "system" if loopback else "mic",
                                     int(info["defaultSampleRate"]), int(info["maxInputChannels"]),
                                     i == (default_loop if loopback else wasapi["defaultInputDevice"])))
            return result

        try:
            self.events.put(("devices", devices()))
            while True:
                try:
                    command, data = self.commands.get_nowait()
                except queue.Empty:
                    command, data = None, {}
                if command:
                    try:
                        close_stream()
                        if command == "shutdown":
                            break
                        if command == "refresh":
                            audio.terminate()
                            audio = pa.PyAudio()
                            self.events.put(("devices", devices()))
                        if command == "start":
                            device = data["device"]
                            generation = data["generation"]
                            gate = data["gate"]
                            ring = np.zeros(1 << math.ceil(math.log2(device.rate * 0.085)), dtype=np.float32)
                            stream = audio.open(format=pa.paFloat32, channels=device.channels,
                                                rate=device.rate, input=True, input_device_index=device.index,
                                                frames_per_buffer=1024, stream_callback=callback)
                            self.events.put(("started", generation))
                        else:
                            self.events.put(("stopped", None))
                    except Exception as exc:
                        close_stream()
                        self.events.put(("error", f"无法打开音频设备：{exc}\n请检查设备连接和麦克风权限，然后刷新设备。"))
                if stream is None:
                    time.sleep(0.02)
                    continue
                try:
                    raw = chunks.get(timeout=0.03)
                except queue.Empty:
                    if not stream.is_active():
                        close_stream()
                        self.events.put(("error", "音频设备已停止，请重新选择设备并开始。"))
                    continue
                mono = strongest_channel(np.frombuffer(raw, dtype=np.float32), device.channels)
                count = min(len(mono), len(ring))
                ring[:-count] = ring[count:]
                ring[-count:] = mono[-count:]
                filled = min(len(ring), filled + count)
                db = 20 * math.log10(max(float(np.sqrt(np.mean(mono * mono))), 1e-12))
                pitch = detect_pitch(ring, device.rate, gate_db=gate) if filled == len(ring) else None
                self.results.append((generation, time.monotonic(), pitch, db))
        except Exception as exc:
            self.events.put(("error", f"音频采集中断：{exc}"))
        finally:
            close_stream()
            audio.terminate()
