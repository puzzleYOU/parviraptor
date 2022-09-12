from setuptools import find_packages, setup

setup(
    name="parviraptor",
    version="0.1.0",
    description="Django-based job queue",
    author="puzzleYOU GmbH",
    packages=find_packages("."),
    install_requires=[
        "Django",
    ],
    zip_safe=True,
)
