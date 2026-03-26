import os
import platform
import stat
import subprocess
import sys

__version__ = "0.1.9"


def _binary_name() -> str:
    system = platform.system()
    machine = platform.machine().lower()
    arch = "arm64" if machine in ("arm64", "aarch64") else "amd64"

    if system == "Windows":
        return f"etherion-tui-windows-{arch}.exe"
    if system == "Darwin":
        return f"etherion-tui-darwin-{arch}"
    return f"etherion-tui-linux-{arch}"


def main():
    bin_dir = os.path.join(os.path.dirname(__file__), "bin")
    binary = os.path.join(bin_dir, _binary_name())

    if not os.path.exists(binary):
        available = os.listdir(bin_dir) if os.path.isdir(bin_dir) else []
        print(
            f"etherion-tui: no binary for your platform "
            f"({platform.system()}/{platform.machine()}).\n"
            f"Expected: {binary}\n"
            f"Available: {', '.join(available) or 'none'}",
            file=sys.stderr,
        )
        sys.exit(1)

    if platform.system() != "Windows":
        current = os.stat(binary).st_mode
        os.chmod(binary, current | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)

    if platform.system() == "Windows":
        sys.exit(subprocess.call([binary] + sys.argv[1:]))
    else:
        os.execv(binary, [binary] + sys.argv[1:])
