"""Compatibility build entrypoint for Python environments with older pip."""

from setuptools import find_packages, setup


setup(
    name="flipper-codex-buddy-bridge",
    version="0.1.0",
    description="Host bridge daemon connecting Flipper Zero to Codex",
    packages=find_packages(include=("bridge", "bridge.*")),
    python_requires=">=3.10",
    install_requires=["pyserial>=3.5", "pyserial-asyncio>=0.6", "bleak>=0.21", "websockets>=14,<17"],
    entry_points={"console_scripts": ["flipper-codex-bridge=bridge.__main__:main"]},
)
