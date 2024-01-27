from setuptools import setup, find_packages  # type: ignore

with open("README.md") as f:
    long_description = f.read()

setup(
    name="rigour",
    version="0.4.0",
    author="OpenSanctions",
    author_email="tech@opensanctions.org",
    url="https://followthemoney.tech/",
    long_description=long_description,
    long_description_content_type="text/markdown",
    license="MIT",
    classifiers=[
        "Intended Audience :: Developers",
        "Operating System :: OS Independent",
        "Programming Language :: Python",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
    ],
    packages=find_packages(exclude=["ez_setup", "examples", "tests"]),
    namespace_packages=[],
    include_package_data=True,
    package_data={
        "": [
            "rigour/py.typed",
        ]
    },
    zip_safe=False,
    install_requires=[
        "babel >= 2.9.1, < 3.0.0",
        "pyyaml >= 5.0.0, < 7.0.0",
        "banal >= 1.0.6, < 1.1.0",
        "normality >= 2.4.0, < 3.0.0",
        "jellyfish >= 1.0.0, < 2.0.0",
        "fingerprints >= 1.0.1, < 2.0.0",
        "python-stdnum >= 1.16, < 2.0.0",
        "pytz >= 2021.1",
    ],
    extras_require={
        "dev": [
            "pip>=10.0.0",
            "bump2version",
            "wheel>=0.29.0",
            "black",
            "twine",
            "mypy",
            "pytest",
            "pytest-cov",
            "types-PyYAML",
            "types-requests",
            "types-setuptools",
            "types-PyYAML",
            "coverage>=4.1",
        ],
        "docs": [
            "pillow",
            "cairosvg",
            "mkdocs",
            "mkdocstrings[python]",
            "mkdocs-material",
        ],
    },
    entry_points={
        "babel.extractors": {},
    },
)
