from setuptools import find_packages, setup

from parviraptor import __version__

setup(
    name="parviraptor",
    version=__version__,
    description="Django-based job queue",
    author="puzzleYOU GmbH",
    packages=find_packages("."),
    install_requires=[
        "Django<5",
    ],
    zip_safe=True,
)
