if __name__ == "__main__":
    import sys
    if len(sys.argv) == 3 and sys.argv[1] == "--self-test":
        import json
        from pathlib import Path
        try:
            import tkinter as tk
            import numpy as np
            import pyaudiowpatch
            from pitchscope.dsp import detect_pitch
            root = tk.Tk()
            root.withdraw()
            root.update()
            root.destroy()
            result = detect_pitch(0.3 * np.sin(2 * np.pi * 440 * np.arange(4096) / 48000), 48000)
            assert result is not None and abs(result.frequency - 440) < 1
            Path(sys.argv[2]).write_text(json.dumps({"ok": True, "frequency": result.frequency}), encoding="utf-8")
        except Exception as exc:
            Path(sys.argv[2]).write_text(json.dumps({"ok": False, "error": str(exc)}), encoding="utf-8")
            raise SystemExit(1)
    else:
        from pitchscope.app import main
        main()
