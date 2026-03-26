"""Cross-platform fat wheel for etherion-tui.

Bundles pre-compiled Go binaries for:
  Linux   x86_64  (etherion-tui-linux-amd64)
  Windows x86_64  (etherion-tui-windows-amd64.exe)
  macOS   x86_64  (etherion-tui-darwin-amd64)
  macOS   arm64   (etherion-tui-darwin-arm64)

Tagged py3-none-any so pip installs it on every platform.
The launcher (__init__.py:main) selects the right binary at runtime.
"""
from setuptools import setup
from wheel.bdist_wheel import bdist_wheel as _bdist_wheel


class bdist_wheel(_bdist_wheel):
    def finalize_options(self):
        super().finalize_options()
        self.root_is_pure = False  # mark as non-pure so binary data is included

    def get_tag(self):
        return "py3", "none", "any"


setup(cmdclass={"bdist_wheel": bdist_wheel})
