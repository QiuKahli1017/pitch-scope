"""Chinese desktop UI, rendered with the Python standard Tk toolkit."""
from collections import deque
import csv
from datetime import datetime
import math
import queue
import time
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from .audio import AudioEngine
from .dsp import note_details

BG = "#101719"
PANEL = "#192326"
FG = "#edf4f0"
MUTED = "#92a7a7"
TEAL = "#77e3be"
GOLD = "#efc580"
FONT = "Microsoft YaHei UI"


class PitchScope(tk.Tk):
    def __init__(self, engine=None):
        super().__init__()
        self.title("PitchScope · 实时音高识别")
        self.geometry("1020x790")
        self.minsize(900, 740)
        self.configure(bg=BG)
        self.engine = engine if engine is not None else AudioEngine()
        self.devices = []
        self.available = []
        self.generation = 0
        self.running = False
        self.last_signal = 0
        self.started_at = 0
        self.pitch_history = deque(maxlen=360)
        self.smoothing = deque(maxlen=3)
        self.records = deque(maxlen=36000)
        self.mode = tk.StringVar(value="system")
        self.note = tk.StringVar(value="—")
        self.frequency = tk.StringVar(value="等待声音")
        self.cents = tk.StringVar(value="偏差  — cents")
        self.quality = tk.StringVar(value="置信度  —")
        self.status = tk.StringVar(value="正在读取音频设备…")
        self.a4 = tk.StringVar(value="440")
        self.gate = tk.StringVar(value="-55")
        self.protocol("WM_DELETE_WINDOW", self.close)
        self._style()
        self._build()
        self.bind("<space>", self._space)
        self.after(50, self._poll)

    def _style(self):
        style = ttk.Style(self)
        style.theme_use("clam")
        style.configure("TCombobox", fieldbackground=PANEL, background=PANEL, foreground=FG,
                        arrowcolor=TEAL, bordercolor="#344448", padding=8, font=(FONT, 10))
        style.map("TCombobox", fieldbackground=[("readonly", PANEL)], foreground=[("readonly", FG)])
        self.option_add("*TCombobox*Listbox.background", PANEL)
        self.option_add("*TCombobox*Listbox.foreground", FG)
        self.option_add("*TCombobox*Listbox.selectBackground", "#31564d")

    def _label(self, parent, text=None, variable=None, size=11, color=FG, bold=False, bg=None):
        return tk.Label(parent, text=text, textvariable=variable, fg=color, bg=bg or parent["bg"],
                        font=(FONT, size, "bold" if bold else "normal"))

    def _button(self, parent, text, command, primary=False):
        return tk.Button(parent, text=text, command=command, bg=TEAL if primary else "#28383b",
                         fg=BG if primary else FG, activebackground="#9aeed1", activeforeground=BG,
                         relief="flat", bd=0, padx=18, pady=10, cursor="hand2", font=(FONT, 10, "bold"))

    def _build(self):
        header = tk.Frame(self, bg=BG)
        header.pack(fill="x", padx=32, pady=(25, 15))
        self._label(header, "PitchScope", size=25, bold=True).pack(side="left")
        self._label(header, "实时音高识别  /  LOCAL AUDIO", size=10, color=TEAL).pack(side="right", pady=12)
        self._label(self, "听见音高的形状。", size=12, color=MUTED).pack(anchor="w", padx=34)

        source = tk.Frame(self, bg=PANEL, padx=20, pady=16)
        source.pack(fill="x", padx=32, pady=(20, 16))
        row = tk.Frame(source, bg=PANEL)
        row.pack(fill="x")
        self._label(row, "01  声音来源", size=10, color=MUTED).pack(side="left", padx=(0, 22))
        for label, value in [("电脑内部声音", "system"), ("麦克风", "mic")]:
            tk.Radiobutton(row, text=label, variable=self.mode, value=value, command=self.change_mode,
                           indicatoron=False, bg="#26363a", fg=FG, selectcolor="#31594d",
                           activebackground="#31594d", activeforeground=FG, relief="flat", bd=0,
                           padx=16, pady=8, font=(FONT, 10), cursor="hand2").pack(side="left", padx=(0, 6))
        self.refresh_button = self._button(row, "刷新设备", self.refresh)
        self.refresh_button.pack(side="right")
        row2 = tk.Frame(source, bg=PANEL)
        row2.pack(fill="x", pady=(12, 0))
        self.device_select = ttk.Combobox(row2, state="readonly", font=(FONT, 10))
        self.device_select.pack(side="left", fill="x", expand=True, padx=(0, 12))
        self.device_select.bind("<<ComboboxSelected>>", self.change_device)
        self.start_button = self._button(row2, "开始识别", self.toggle, primary=True)
        self.start_button.pack(side="right")

        readout = tk.Frame(self, bg=PANEL, padx=20, pady=14)
        readout.pack(fill="x", padx=32)
        self._label(readout, "02  当前音高", size=10, color=MUTED).pack(anchor="w")
        center = tk.Frame(readout, bg=PANEL)
        center.pack(fill="x")
        self._label(center, variable=self.note, size=66, color=TEAL, bold=True).pack(side="left", padx=(18, 30))
        details = tk.Frame(center, bg=PANEL)
        details.pack(side="left", pady=12)
        self._label(details, variable=self.frequency, size=24, bold=True).pack(anchor="w")
        self._label(details, variable=self.cents, size=12, color=GOLD).pack(anchor="w", pady=(7, 0))
        self._label(details, variable=self.quality, size=10, color=MUTED).pack(anchor="w", pady=3)
        self.meter = tk.Canvas(readout, bg=PANEL, height=62, highlightthickness=0)
        self.meter.pack(fill="x")
        self.meter.bind("<Configure>", lambda _: self._draw_meter(None))

        chart_panel = tk.Frame(self, bg=PANEL, padx=20, pady=15)
        chart_panel.pack(fill="both", expand=True, padx=32, pady=16)
        chart_header = tk.Frame(chart_panel, bg=PANEL)
        chart_header.pack(fill="x")
        self._label(chart_header, "03  音高轨迹", size=10, color=MUTED).pack(side="left")
        self._label(chart_header, "最近 12 秒 · 半音刻度", size=9, color=MUTED).pack(side="right")
        self.chart = tk.Canvas(chart_panel, bg=PANEL, height=130, highlightthickness=0)
        self.chart.pack(fill="both", expand=True, pady=(10, 0))

        settings = tk.Frame(self, bg=BG)
        settings.pack(fill="x", padx=32)
        self._label(settings, "A4 基准", size=10, color=MUTED).pack(side="left")
        self.reference_input = tk.Spinbox(settings, from_=400, to=480, increment=1, width=5,
                                        textvariable=self.a4, bg=PANEL, fg=FG, buttonbackground=PANEL,
                                        relief="flat", font=(FONT, 11), insertbackground=FG)
        self.reference_input.pack(side="left", padx=(8, 4))
        self._label(settings, "Hz", size=10, color=MUTED).pack(side="left", padx=(0, 24))
        self._label(settings, "静音门限", size=10, color=MUTED).pack(side="left")
        self.gate_input = tk.Spinbox(settings, from_=-80, to=-20, increment=5, width=5,
                                   textvariable=self.gate, bg=PANEL, fg=FG, buttonbackground=PANEL,
                                   relief="flat", font=(FONT, 11), insertbackground=FG)
        self.gate_input.pack(side="left", padx=(8, 4))
        self._label(settings, "dBFS", size=10, color=MUTED).pack(side="left")
        self._button(settings, "导出 CSV", self.export).pack(side="right")
        footer = tk.Frame(self, bg=BG)
        footer.pack(fill="x", padx=32, pady=(12, 18))
        self.status_label = self._label(footer, variable=self.status, size=9, color=MUTED)
        self.status_label.pack(side="left")
        self._label(footer, "单音识别 · 音频仅在本地处理", size=9, color=MUTED).pack(side="right")

    def _space(self, event):
        if isinstance(event.widget, (tk.Spinbox, ttk.Combobox, tk.Entry, tk.Button)):
            return
        self.toggle()
        return "break"

    def _settings(self):
        try:
            ref, gate = float(self.a4.get()), float(self.gate.get())
            if not 400 <= ref <= 480 or not -80 <= gate <= -20:
                raise ValueError
            return ref, gate
        except ValueError:
            messagebox.showerror("参数有误", "A4 基准应为 400–480 Hz；静音门限应为 -80 至 -20 dBFS。")
            return None

    def _choose_devices(self):
        self.available = [d for d in self.devices if d.mode == self.mode.get()]
        self.device_select["values"] = [d.name + (" · 默认" if d.default else "") for d in self.available]
        if self.available:
            self.device_select.current(next((i for i, d in enumerate(self.available) if d.default), 0))
            self.status.set("就绪 · 按空格或点击开始识别")
        else:
            self.device_select.set("")
            self.status.set("未找到设备 · 请连接设备后刷新")

    def change_mode(self):
        resume = self.running
        self.stop()
        self._choose_devices()
        if resume and self.available:
            self.start()

    def change_device(self, _event=None):
        if self.running:
            self.stop()
            self.start()

    def refresh(self):
        self.stop()
        self.devices = []
        self._choose_devices()
        self.status.set("正在刷新设备…")
        self.engine.request("refresh")

    def toggle(self):
        self.stop() if self.running else self.start()

    def start(self):
        settings = self._settings()
        if settings is None:
            return
        index = self.device_select.current()
        if not 0 <= index < len(self.available):
            self.status.set("请先选择可用设备")
            return
        self.reference, gate = settings
        self.generation += 1
        self.running = True
        self.started_at = time.monotonic()
        self.last_signal = self.started_at
        self.pitch_history.clear()
        self.smoothing.clear()
        self.start_button.configure(text="停止识别")
        self.reference_input.configure(state="disabled")
        self.gate_input.configure(state="disabled")
        self.status.set("正在打开音频设备…")
        self.engine.request("start", device=self.available[index], generation=self.generation, gate=gate)

    def stop(self):
        self.running = False
        self.generation += 1
        self.engine.request("stop")
        self.start_button.configure(text="开始识别")
        self.reference_input.configure(state="normal")
        self.gate_input.configure(state="normal")
        self.status.set("已停止 · 音频设备已请求释放")
        self._clear_readout()

    def _clear_readout(self):
        self.note.set("—")
        self.frequency.set("等待稳定单音" if self.running else "等待声音")
        self.cents.set("偏差  — cents")
        self.quality.set("置信度  —")
        self.smoothing.clear()
        self._draw_meter(None)

    def _draw_meter(self, cents):
        canvas = self.meter
        canvas.delete("all")
        width = max(canvas.winfo_width(), 100)
        left, right, y = 30, width - 30, 23
        x = lambda c: left + (c + 50) / 100 * (right - left)
        canvas.create_rectangle(x(-5), y - 9, x(5), y + 9, fill="#284c41", outline="")
        canvas.create_line(left, y, right, y, fill="#536367", width=2)
        for value in (-50, -25, 0, 25, 50):
            canvas.create_line(x(value), y - 6, x(value), y + 6, fill=MUTED)
            canvas.create_text(x(value), y + 22, text=f"{value:+d}" if value else "准确", fill=MUTED, font=(FONT, 9))
        if cents is not None:
            cx = x(max(-50, min(50, cents)))
            canvas.create_oval(cx - 6, y - 6, cx + 6, y + 6, fill=TEAL if abs(cents) <= 5 else GOLD, outline="")

    def _draw_chart(self):
        canvas = self.chart
        canvas.delete("all")
        width, height = max(canvas.winfo_width(), 100), max(canvas.winfo_height(), 80)
        now = time.monotonic()
        visible = [(t, midi) for t, midi in self.pitch_history if now - t <= 12]
        notes = [m for _, m in visible if m is not None]
        center = round(sum(notes) / len(notes)) if notes else 69
        span = max(6, math.ceil(max((abs(m - center) for m in notes), default=0)) + 1)
        top, bottom = center + span, center - span
        y = lambda m: 8 + (top - m) / (top - bottom) * (height - 26)
        for midi in range(bottom, top + 1, max(1, math.ceil(span / 4))):
            name = note_details(440 * 2 ** ((midi - 69) / 12))[0]
            canvas.create_text(2, y(midi), anchor="w", text=name, fill=MUTED, font=(FONT, 8))
            canvas.create_line(40, y(midi), width - 8, y(midi), fill="#2a373a")
        for seconds in (12, 9, 6, 3, 0):
            xx = 42 + (12 - seconds) / 12 * (width - 52)
            canvas.create_text(xx, height - 5, text=f"-{seconds}s" if seconds else "现在", fill=MUTED, font=(FONT, 8))
        previous = None
        for timestamp, midi in visible:
            if midi is None:
                previous = None
                continue
            xx = 42 + (12 - (now - timestamp)) / 12 * (width - 52)
            yy = y(midi)
            if previous and timestamp - previous[2] < 0.25:
                canvas.create_line(previous[0], previous[1], xx, yy, fill=TEAL, width=2)
            previous = xx, yy, timestamp
        if not notes:
            canvas.create_text(width / 2, height / 2 - 8, text="播放音乐单音，或对麦克风哼唱", fill=MUTED, font=(FONT, 11))

    def _poll(self):
        while True:
            try:
                event, data = self.engine.events.get_nowait()
            except queue.Empty:
                break
            if event == "devices":
                self.devices = data
                self._choose_devices()
            elif event == "started" and self.running and data == self.generation:
                self.status.set("正在识别 · " + ("电脑内部声音" if self.mode.get() == "system" else "麦克风"))
            elif event == "error":
                self.stop()
                self.status.set("音频设备错误 · 请刷新设备后重试")
                messagebox.showerror("音频设备错误", data)
        try:
            generation, timestamp, pitch, db = self.engine.results.popleft()
        except IndexError:
            pitch = None
            generation = -1
        if self.running and generation == self.generation:
            self.last_signal = timestamp
            if pitch:
                # Smooth tiny jitter only; keep semitone jumps and note attacks responsive.
                if self.smoothing and abs(12 * math.log2(pitch.frequency / self.smoothing[-1])) > 0.6:
                    self.smoothing.clear()
                self.smoothing.append(pitch.frequency)
                frequency = sorted(self.smoothing)[len(self.smoothing) // 2]
                name, cents, _, midi = note_details(frequency, self.reference)
                self.note.set(name)
                self.frequency.set(f"{frequency:.2f} Hz")
                self.cents.set(f"{cents:+.1f} cents  ·  " + ("音准稳定" if abs(cents) <= 5 else "偏高" if cents > 0 else "偏低"))
                self.quality.set(f"置信度  {pitch.confidence:.0%}    /    输入电平  {db:.0f} dBFS")
                self._draw_meter(cents)
                self.pitch_history.append((timestamp, midi))
                self.records.append((datetime.now().isoformat(timespec="milliseconds"), self.mode.get(),
                                     self.available[self.device_select.current()].name, round(frequency, 3), name,
                                     round(cents, 2), round(pitch.confidence, 4), round(db, 2), self.reference))
            else:
                self._clear_readout()
                self.quality.set(f"输入电平  {db:.0f} dBFS  ·  等待清晰的周期信号")
                self.pitch_history.append((timestamp, None))
        elif self.running and time.monotonic() - self.last_signal > 0.5:
            self._clear_readout()
            self.status.set("等待音频 · 请播放声音，或检查所选设备")
            self.pitch_history.append((time.monotonic(), None))
        if self.running and generation == self.generation:
            self.status.set("正在识别 · " + ("电脑内部声音" if self.mode.get() == "system" else "麦克风"))
        self._draw_chart()
        self.after(40, self._poll)

    def export(self):
        if not self.records:
            messagebox.showinfo("暂无数据", "开始识别并获得有效音高后，即可导出 CSV。")
            return
        path = filedialog.asksaveasfilename(title="导出音高记录", defaultextension=".csv",
                                          initialfile=f"pitchscope-{datetime.now():%Y%m%d-%H%M%S}.csv",
                                          filetypes=[("CSV 文件", "*.csv")])
        if not path:
            return
        try:
            with open(path, "w", encoding="utf-8-sig", newline="") as f:
                writer = csv.writer(f)
                writer.writerow(["timestamp", "mode", "device", "frequency_hz", "note", "cents", "confidence", "dbfs", "a4_hz"])
                writer.writerows(list(self.records))
            self.status.set(f"已导出 {len(self.records)} 条音高记录")
        except OSError as exc:
            messagebox.showerror("导出失败", str(exc))

    def close(self):
        self.engine.request("shutdown")
        self.withdraw()
        self._wait_for_close(time.monotonic())

    def _wait_for_close(self, started):
        if not self.engine.thread.is_alive() or time.monotonic() - started > 3:
            self.destroy()
        else:
            self.after(30, lambda: self._wait_for_close(started))


def main():
    import sys
    if sys.platform != "win32":
        raise SystemExit("PitchScope currently supports Windows 10/11 only.")
    import ctypes
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except (OSError, AttributeError):
        pass
    app = PitchScope()
    app.mainloop()
