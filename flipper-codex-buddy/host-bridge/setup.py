"""Compatibility build entrypoint for Python environments with older pip."""

from setuptools import find_packages, setup


setup(
    name="flipper-agent-buddy-codex-bridge",
    version="0.1.0",
    description="Codex adapter bridge for Flipper Agent Buddy",
    packages=find_packages(include=("bridge", "bridge.*")),
    python_requires=">=3.10",
    install_requires=["pyserial>=3.5", "pyserial-asyncio>=0.6", "bleak>=0.21", "websockets>=14,<17"],
    entry_points={"console_scripts": ["flipper-agent-codex-bridge=bridge.__main__:main"]},
)
