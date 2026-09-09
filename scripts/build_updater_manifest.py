from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import quote


VALID_TARGETS = {
    "linux-x86_64",
    "linux-aarch64",
    "darwin-x86_64",
    "darwin-aarch64",
    "windows-x86_64",
    "windows-aarch64",
}


def _safe_asset_path(metadata_path: Path, value: object, field: str) -> Path:
    if not isinstance(value, str) or not value or Path(value).name != value:
        raise ValueError(f"Invalid updater {field} beside {metadata_path}")
    return metadata_path.parent / value


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("artifacts", type=Path)
    parser.add_argument("--repository", required=True)
    parser.add_argument("--tag", required=True)
    parser.add_argument("--version", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    platforms: dict[str, dict[str, str]] = {}
    for metadata_path in args.artifacts.rglob("updater-metadata.json"):
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        target = metadata.get("target")
        if target not in VALID_TARGETS:
            raise ValueError(f"Invalid updater target beside {metadata_path}: {target!r}")
        if target in platforms:
            raise ValueError(f"Duplicate updater target: {target}")
        bundle = _safe_asset_path(metadata_path, metadata.get("bundle"), "bundle")
        signature = _safe_asset_path(metadata_path, metadata.get("signature"), "signature")
        if not bundle.is_file() or not signature.is_file():
            raise ValueError(f"Updater files missing beside {metadata_path}")
        signature_text = signature.read_text(encoding="utf-8").strip()
        if not signature_text:
            raise ValueError(f"Updater signature is empty: {signature}")
        asset_name = bundle.name
        platforms[target] = {
            "signature": signature_text,
            "url": (
                f"https://github.com/{args.repository}/releases/download/"
                f"{quote(args.tag)}/{quote(asset_name)}"
            ),
        }
    if not platforms:
        raise ValueError("No updater metadata found")
    args.output.write_text(
        json.dumps(
            {
                "version": args.version,
                "notes": f"Ops Agent {args.tag}",
                "pub_date": datetime.now(UTC).isoformat(),
                "platforms": platforms,
            },
            ensure_ascii=False,
            indent=2,
        ) + "\n",
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
