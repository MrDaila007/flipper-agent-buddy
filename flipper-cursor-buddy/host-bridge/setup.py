"""Compatibility build entrypoint for Python environments with older pip."""

from setuptools import find_packages, setup


setup(
    name="flipper-cursor-buddy-bridge",
    version="0.1.0",
    description="Host bridge daemon connecting Flipper Zero to Cursor",
    packages=find_packages(include=("bridge", "bridge.*")),
    python_requires=">=3.10",
    install_requires=["pyserial>=3.5", "pyserial-asyncio>=0.6", "bleak>=0.21"],
    entry_points={"console_scripts": ["flipper-cursor-bridge=bridge.__main__:main"]},
)
