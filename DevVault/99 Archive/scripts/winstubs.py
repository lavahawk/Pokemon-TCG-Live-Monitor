# Test-only stubs for Windows modules so the app's modules import on Linux.
import sys, types
for name in ("win32gui","win32process","win32con","win32api"):
    if name not in sys.modules:
        m = types.ModuleType(name)
        def _f(*a, **k): return 0
        m.__getattr__ = lambda attr, _f=_f: _f
        sys.modules[name] = m
try:
    import tkinter  # noqa
except Exception:
    tk = types.ModuleType("tkinter"); tk.simpledialog = types.ModuleType("tkinter.simpledialog")
    tk.messagebox = types.ModuleType("tkinter.messagebox")
    sys.modules["tkinter"] = tk; sys.modules["tkinter.simpledialog"] = tk.simpledialog; sys.modules["tkinter.messagebox"] = tk.messagebox
