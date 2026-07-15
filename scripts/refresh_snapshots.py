#!/usr/bin/env python3
"""Refresh the bundled snapshots for ALL SNIRH networks (maintainer script).

Iterates every network from live discovery and rewrites its bundled
snapshot (``snapshot_<slug>.csv``) through the package's own code path
(:meth:`Snirh.refresh_snapshot`). One Snirh instance per network, strictly
sequential and polite to SNIRH: ~4 requests per network, ~60 in total, with
a short pause between networks.

Coordinate-less networks (e.g. ``eta``, ``hidrometrica_madeira``) are
snapshotted too — their ``latitude``/``longitude`` columns are NaN because
those stations never appear on the SNIRH map layer.

Usage::

    python scripts/refresh_snapshots.py [output_dir]

With no argument the snapshots bundled inside the installed package are
refreshed (editable install -> the repo's ``src/get_snirh/data/``).
"""

import sys
import time

from get_snirh import Snirh, SnirhError
from get_snirh.snapshots import load_snapshot, snapshot_date

#: Pause between networks, out of politeness to SNIRH.
PAUSE_SECONDS = 1.0


def main(output_dir=None) -> int:
    print("Discovering SNIRH networks (live)...")
    networks = Snirh().networks()
    print(f"  {len(networks)} networks discovered.\n")

    written, failed = [], []
    for i, row in enumerate(networks.itertuples(index=False), start=1):
        prefix = f"[{i:2d}/{len(networks)}] {row.slug}"
        snirh = Snirh(row.slug)
        # Reuse the discovery result: saves one home-page request/network.
        snirh._networks_cache = networks.copy()
        try:
            path = snirh.refresh_snapshot(output_dir)
        except SnirhError as exc:
            print(f"{prefix}: FAILED — {exc}")
            failed.append(row.slug)
        else:
            df = load_snapshot(row.slug, output_dir)
            coords = "no coordinates" if df["latitude"].isna().all() \
                else "with coordinates"
            print(f"{prefix}: {len(df)} stations ({coords}) "
                  f"fetched {snapshot_date(row.slug, output_dir)} -> {path}")
            written.append((row.slug, len(df), path))
        if i < len(networks):
            time.sleep(PAUSE_SECONDS)

    print(f"\nSummary: {len(written)} snapshots written, {len(failed)} failed.")
    for slug, rows, path in written:
        print(f"  {slug}: {rows} stations ({path})")
    if failed:
        print("Failed networks: " + ", ".join(failed))
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1] if len(sys.argv) > 1 else None))
