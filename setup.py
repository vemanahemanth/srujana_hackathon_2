from setuptools import setup, find_packages

setup(
    name="fragilityshield",
    version="1.0.0",
    description="Universal External Connectivity SDK and Quantitative Analysis Platform",
    package_dir={"": "backend"},
    packages=find_packages(where="backend"),
    install_requires=[
        "numpy>=1.24.0",
        "scipy>=1.10.0",
    ],
    python_requires=">=3.10",
)
