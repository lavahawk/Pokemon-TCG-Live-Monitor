"""Run every test_*.py next to this file, each in its own Python process.

    .venv\\Scripts\\python.exe run_tests.py [-v] [name_filter ...]

Prints one summary line per file and the totals; exits 1 when any file
fails (non-zero exit or a FAIL line), else 0. -v shows each file's output.
"""
import glob
import os
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))


def main(argv):
    verbose = "-v" in argv
    filters = [a for a in argv if not a.startswith("-")]
    files = sorted(glob.glob(os.path.join(HERE, "test_*.py")))
    if filters:
        files = [f for f in files if any(x in os.path.basename(f) for x in filters)]
    if not files:
        print("No test files found.")
        return 1
    env = dict(os.environ, PYTHONIOENCODING="utf-8", QT_QPA_PLATFORM="offscreen", PTCGL_NO_PROMPT="1")
    totals = {"PASS": 0, "FAIL": 0, "SKIP": 0}
    broken = []
    for path in files:
        name = os.path.basename(path)
        start = time.monotonic()
        proc = subprocess.run([sys.executable, path], cwd=HERE, env=env, stdin=subprocess.DEVNULL,
                              capture_output=True, text=True, encoding="utf-8", errors="replace")
        counts = {"PASS": 0, "FAIL": 0, "SKIP": 0}
        for line in proc.stdout.splitlines():
            word = line.split(" ", 1)[0]
            if word in counts:
                counts[word] += 1
        for key in totals:
            totals[key] += counts[key]
        ok = proc.returncode == 0 and counts["FAIL"] == 0
        if not ok:
            broken.append(name)
        print(f"{'ok  ' if ok else 'FAIL'} {name:<26} {counts['PASS']} passed, {counts['FAIL']} failed, "
              f"{counts['SKIP']} skipped ({time.monotonic() - start:.1f}s)")
        if verbose or not ok:
            for line in proc.stdout.splitlines():
                if verbose or not line.startswith(("PASS", "SKIP")):
                    print("    " + line)
            if proc.stderr.strip() and (verbose or not ok):
                print("    [stderr]\n" + "\n".join("    " + l for l in proc.stderr.strip().splitlines()[-30:]))
    print(f"\n{len(files)} files: {totals['PASS']} passed, {totals['FAIL']} failed, {totals['SKIP']} skipped"
          + (f"; failing files: {', '.join(broken)}" if broken else ""))
    return 1 if broken else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
