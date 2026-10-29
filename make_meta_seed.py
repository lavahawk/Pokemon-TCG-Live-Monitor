"""Packs the Limitless event caches (.meta_store) into meta_seed.zip, which
the installer ships: on first run meta_sources.unpack_seed() puts them in
the new install's .meta_store, so it starts with months of events instead
of the few the API limit allows per refresh. Run by build_installer.ps1:
    python make_meta_seed.py <.meta_store dir> <out zip>
"""
import os
import re
import sys
import zipfile

# Per-event caches never go stale; index files (expansions, Labs index,
# last_inputs) have TTLs or describe one machine's last build, so they stay out.
EVENT_FILE = re.compile(r"^(online_v3|inperson_v2|inperson_lists|inperson_standings_v2|japan|labs)_.+\.json$")


def main(store, out):
    names = sorted(n for n in os.listdir(store) if EVENT_FILE.match(n))
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as seed:
        for name in names:
            seed.write(os.path.join(store, name), name)
    print(f"{len(names)} events, {os.path.getsize(out) / 1e6:.1f} MB -> {out}")


if __name__ == "__main__":
    main(*sys.argv[1:3])
