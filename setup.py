import re
from setuptools import setup

with open("requirements.txt") as f:
    requirements = f.read().splitlines()

with open("snakecore/__init__.py") as f:
    searched = re.search(
        r'^__version__\s*=\s*[\'"]([^\'"]*)[\'"]', f.read(), re.MULTILINE
    )
    version = searched.group(1) if searched is not None else ""
    if not version:
        raise RuntimeError("version is not set")

with open("README.md") as f:
    readme = f.read()

packages = [
    "snakecore",
    "snakecore.commands",
    "snakecore.constants",
    "snakecore.storage",
    "snakecore._events",
    "snakecore._jobs",
    "snakecore._jobutils",
    "snakecore.utils",
]

setup(
    name="snakecore",
    author="pygame-community",
    url="https://github.com/pygame-community/snakecore",
    project_urls={
        "Issue tracker": "https://github.com/pygame-community/snakecore/issues",
    },
    version=version,
    packages=packages,
    license="MIT",
    description=(
        "A set of core APIs to facilitate the creation of feature-rich Discord bots."
    ),
    long_description=readme,
    long_description_content_type="text/markdown",
    include_package_data=True,
    install_requires=requirements,
    python_requires=">=3.9.0",
    platforms=["any"],
    classifiers=[
        "Topic :: Software Development",
        "License :: OSI Approved :: MIT License",
        "Intended Audience :: Developers",
        "Natural Language :: English",
        "Operating System :: OS Independent",
        "Programming Language :: Python :: 3.9",
        "Programming Language :: Python :: 3.10",
        "Development Status :: 2 - Pre-Alpha",
        "Topic :: Internet",
        "Topic :: Software Development :: Libraries",
        "Topic :: Software Development :: Libraries :: Python Modules",
        "Topic :: Utilities",
        "Typing :: Typed",
    ],
)
