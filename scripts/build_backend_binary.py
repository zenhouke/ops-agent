#!/usr/bin/env python3
from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path


def run(cmd: list[str], cwd: Path) -> None:
    subprocess.run(cmd, cwd=str(cwd), check=True)


def main() -> None:
    parser = argparse.ArgumentParser(description="Build backend executable for desktop bundles")
    parser.add_argument("--platform", choices=["macos", "linux", "windows"], required=True)
    args = parser.parse_args()

    repo_root = Path(__file__).resolve().parents[1]
    dist_dir = repo_root / "dist"
    build_dir = repo_root / "build"
    pyinstaller_spec = repo_root / "ops-agent-backend.spec"

    binary_name = "ops-agent-backend.exe" if args.platform == "windows" else "ops-agent-backend"
    target_bin_dir = repo_root / "web" / "bin"
    target_bin_dir.mkdir(parents=True, exist_ok=True)
    target_binary = target_bin_dir / binary_name

    # clean prior artifacts
    if dist_dir.exists():
        shutil.rmtree(dist_dir)
    if build_dir.exists():
        shutil.rmtree(build_dir)
    if pyinstaller_spec.exists():
        pyinstaller_spec.unlink()

    pyinstaller_cmd = [
        sys.executable,
        "-m",
        "PyInstaller",
        "--noconfirm",
        "--clean",
        "--onefile",
        "--name",
        "ops-agent-backend",
        "--paths",
        "src",
        "--add-data",
        f"{repo_root / 'src' / 'app' / 'plugins' / 'builtin'}{os.pathsep}app/plugins/builtin",
        "src/app/main.py",
    ]
    run(pyinstaller_cmd, repo_root)

    built_binary = dist_dir / binary_name
    if not built_binary.exists():
        raise FileNotFoundError(f"Backend binary not found: {built_binary}")

    if target_binary.exists():
        target_binary.unlink()
    shutil.copy2(built_binary, target_binary)

    if args.platform != "windows":
        target_binary.chmod(0o755)

    print(f"Built backend binary: {target_binary}")


if __name__ == "__main__":
    main()
