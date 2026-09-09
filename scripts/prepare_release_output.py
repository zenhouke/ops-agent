from __future__ import annotations

import argparse
import json
import platform
import shutil
from pathlib import Path


PATTERNS = {
    "linux": "*.AppImage.sig",
    "macos": "*.app.tar.gz.sig",
    "windows": "*.exe.sig",
}


def updater_target(release_platform: str) -> str:
    machine = platform.machine().lower()
    architecture = "aarch64" if machine in {"arm64", "aarch64"} else "x86_64"
    family = {"linux": "linux", "macos": "darwin", "windows": "windows"}[release_platform]
    return f"{family}-{architecture}"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--platform", choices=sorted(PATTERNS), required=True)
    parser.add_argument("--bundle-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    signatures = list(args.bundle_root.rglob(PATTERNS[args.platform]))
    if len(signatures) != 1:
        raise ValueError(f"Expected one updater signature, found {len(signatures)}")
    signature = signatures[0]
    bundle = signature.with_suffix("")
    if not bundle.is_file():
        raise ValueError(f"Updater bundle missing: {bundle}")
    args.output.mkdir(parents=True, exist_ok=True)
    copied_bundle = args.output / bundle.name
    copied_signature = args.output / signature.name
    shutil.copy2(bundle, copied_bundle)
    shutil.copy2(signature, copied_signature)
    (args.output / "updater-metadata.json").write_text(
        json.dumps(
            {
                "target": updater_target(args.platform),
                "bundle": copied_bundle.name,
                "signature": copied_signature.name,
            },
            indent=2,
        ) + "\n",
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
