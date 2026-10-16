"""
Build-time smoke test of the staged installer bundle.

Run with the STAGED runtime (isolated mode):
    <stage>\\runtime\\python.exe -I installer\\smoke_test.py <stage>

Proves the trimmed runtime still has everything the app needs: every app
module imports, Qt WebEngine actually renders a page, and Tesseract reads text.
Exits non-zero on the first failure so a broken bundle never ships.
"""

import importlib
import os
import sys
import time

STAGE = os.path.abspath(sys.argv[1])
sys.path.insert(0, STAGE)
os.chdir(STAGE)

failures = []


def check(name, fn):
    t0 = time.time()
    try:
        detail = fn()
        print(f"    ok    {name}" + (f"  ({detail})" if detail else "") + f"  [{time.time() - t0:.1f}s]")
    except Exception as exc:  # report every failure, not just the first
        failures.append(name)
        print(f"    FAIL  {name}: {type(exc).__name__}: {exc}")


# 1. Third-party packages the app imports.
for mod in ("PySide6.QtCore", "PySide6.QtGui", "PySide6.QtWidgets", "PySide6.QtTest",
            "PySide6.QtWebEngineCore", "PySide6.QtWebEngineWidgets", "PySide6.QtNetwork",
            "PySide6.QtPdf", "PySide6.QtPrintSupport", "cv2", "numpy", "mss",
            "pytesseract", "psutil", "pyperclip", "win32gui", "win32process", "win32con", "matplotlib",
            "openpyxl", "pandas", "requests", "bs4", "lxml", "openai", "pygame", "pyfiglet",
            "colorama", "PIL", "sqlite3", "ssl", "ctypes"):
    check(f"import {mod}", lambda m=mod: importlib.import_module(m) and None)

# 2. Every shipped app module imports (catches a module missing from the manifest).
for fname in sorted(os.listdir(STAGE)):
    if fname.endswith(".py"):
        mod = fname[:-3]
        check(f"app module {mod}", lambda m=mod: importlib.import_module(m) and None)


# 3. Qt WebEngine renders a page offscreen (the dashboard's web tabs need it).
def webengine():
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    os.environ.setdefault("QTWEBENGINE_CHROMIUM_FLAGS", "--disable-gpu")
    from PySide6.QtCore import QTimer, QUrl
    from PySide6.QtWebEngineWidgets import QWebEngineView
    from PySide6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication([])
    view = QWebEngineView()
    result = {}

    def loaded(ok):
        view.page().runJavaScript("document.getElementById('x').textContent",
                                  lambda text: (result.update(ok=ok, text=text), app.quit()))

    view.loadFinished.connect(loaded)
    view.setHtml("<html><body><p id='x'>webengine-ok</p></body></html>", QUrl("about:blank"))
    QTimer.singleShot(30000, app.quit)
    app.exec()
    if result.get("text") != "webengine-ok":
        raise RuntimeError(f"page did not render: {result}")
    return "rendered"


check("Qt WebEngine render", webengine)


# 4. Tesseract OCR from the bundled folder.
def tesseract():
    import numpy as np
    import cv2
    import pytesseract
    from RankDetector import _find_tesseract
    exe = _find_tesseract()
    if not exe.lower().startswith(STAGE.lower()):
        raise RuntimeError(f"not using the bundled Tesseract: {exe}")
    pytesseract.pytesseract.tesseract_cmd = exe
    img = np.full((80, 360), 255, np.uint8)
    cv2.putText(img, "BATTLE LOG 1446", (10, 55), cv2.FONT_HERSHEY_SIMPLEX, 1.2, 0, 3)
    text = pytesseract.image_to_string(img, config="--psm 7").strip()
    if "BATTLE" not in text.upper():
        raise RuntimeError(f"unexpected OCR result {text!r}")
    return repr(text)


check("Tesseract OCR", tesseract)


# 5. The battle-log button verifier accepts the shipped template.
def template_ocr():
    import cv2
    from BattleEndAutomation import reads_battle_log
    tpl = cv2.imread(os.path.join(STAGE, "button_templates", "battle_log.png"), cv2.IMREAD_GRAYSCALE)
    if tpl is None:
        return "no template shipped - skipped"
    if not reads_battle_log(tpl):
        raise RuntimeError("BATTLE LOG template not recognised")
    return "recognised"


check("BATTLE LOG text check", template_ocr)

if failures:
    print(f"\nSMOKE TEST FAILED: {len(failures)} problem(s): {', '.join(failures)}")
    sys.exit(1)
print("\nSmoke test passed.")
