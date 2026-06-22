from setuptools import find_packages, setup

setup(
    name="crypto-futures-monitor-alert",
    version="0.1.0",
    package_dir={"": "src"},
    packages=find_packages(where="src"),
    python_requires=">=3.8",
    install_requires=[
        "httpx>=0.27,<1",
        "websockets>=12,<14",
        "PyYAML>=6,<7",
        "aiohttp>=3.9,<4",
    ],
    entry_points={
        "console_scripts": [
            "futures-monitor=crypto_futures_monitor.main:main",
        ],
    },
)
