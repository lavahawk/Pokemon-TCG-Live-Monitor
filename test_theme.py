"""Tests for theme.py (run: python test_theme.py). Pure stylesheet / colour
mapping; no window is shown."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import theme as T

CSS = ("QLabel { color: #66BB6A; background: rgba(74, 159, 216, 0.18); border: 1px solid #4a9fd8; "
       "border-radius: 8px; border-top-left-radius: 3px; font-family: 'Segoe UI', Arial; } "
       "QFrame { background: qlineargradient(x1:0, y1:0, stop:0 rgba(15, 15, 15, __GLASS_TOP__)); "
       "border-radius: 20px; font-family: Consolas, monospace; }")


def use(key):
    T._current, T._parts = key, T.THEMES[key]
    T._seen.clear()
    T._loaded_families.update({"Geist", "Geist Mono", "Mona Sans", "JetBrains Mono"})


def test_legacy_changes_nothing():
    use("legacy")
    assert T.css(CSS) == CSS
    assert T.family("ui") == "Segoe UI" and T.family("mono") == "Consolas"


def test_primer_maps_roles_keeps_alpha_and_placeholders():
    use("primer")
    out = T.css(CSS)
    assert "#3fb950" in out and "#66BB6A" not in out                        # win
    assert "rgba(68, 147, 248, 0.18)" in out and "#4493f8" in out          # accent, alpha kept
    assert "rgba(13, 17, 23, __GLASS_TOP__)" in out                        # background, placeholder kept
    assert "border-radius: 12px" in out and "border-top-left-radius: 3px" in out
    assert "border-radius: 20px" in out                                    # pills untouched
    assert "font-family: 'Mona Sans', 'Segoe UI', 'Arial'" in out
    assert "'JetBrains Mono', 'Consolas', monospace" in out


def test_mix_takes_each_part_from_its_source():
    use("geist_primer_geist")
    out = T.css(CSS)
    assert "#3fb950" in out                                                # Primer colours
    assert "'Geist', 'Segoe UI'" in out and "'Geist Mono', 'Consolas'" in out
    assert "border-radius: 8px" in out and "border-top-left-radius: 4px" in out  # Geist corners
    use("primer_geist_valorant")
    out = T.css(CSS)
    assert "#46a758" in out and "rgba(0, 0, 0, __GLASS_TOP__)" in out     # Geist colours
    assert "border-radius: 0px" in out and "border-top-left-radius: 0px" in out
    assert "border-radius: 20px" in out


def test_rewriting_twice_is_stable():
    use("primer")
    once = T.css(CSS)
    assert T.css(once) == once


def test_qcolor_arguments():
    use("primer")
    assert T._mapped_args(("#4A9FD8",)) == ("#4493f8",)
    assert T._mapped_args(("#80ef5350",)) == ("#80f85149",)
    assert T._mapped_args((239, 83, 80, 90)) == (248, 81, 73, 90)
    assert T._mapped_args(("#123456",)) == ("#123456",)
    assert T._mapped_args((0, 200, 200)) == (0, 200, 200)            # unrelated colour
    assert T._mapped_args((255, 167, 38)) != (255, 167, 38)          # computed shade of amber


def test_missing_fonts_fall_back():
    use("primer")
    T._loaded_families.clear()
    assert T.family("ui") == "Segoe UI"
    assert "'Segoe UI', 'Arial'" in T.css("QLabel { font-family: 'Segoe UI', Arial; }")


def test_unknown_theme_is_legacy():
    assert T.theme_key({"ui_theme": "nope"}) == "legacy" and T.theme_key({}) == "legacy"
    assert T.theme_key({"ui_theme": "primer"}) == "primer"


if __name__ == "__main__":
    failures = 0
    for name, fn in list(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                print(f"PASS {name}")
            except Exception as exc:
                failures += 1
                print(f"FAIL {name}: {type(exc).__name__}: {exc}")
    sys.exit(1 if failures else 0)
