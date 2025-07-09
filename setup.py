from setuptools import find_packages, setup

from parviraptor import __version__

setup(
    name="parviraptor",
    version=__version__,
    description="Django-based job queue",
    long_description=open("README.md").read(),
    long_description_content_type="text/markdown",
    author="puzzleYOU GmbH",
    url="https://github.com/puzzleYOU/parviraptor",
    license="MIT",
    packages=find_packages("."),
    install_requires=[
        "Django<5",
    ],
    zip_safe=True,
)
