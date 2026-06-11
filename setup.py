from setuptools import find_packages, setup

from parviraptor import __version__

setup(
    name="parviraptor",
    version=__version__,
    description="Django-based job queue",
    include_package_data=True,
    long_description=open("README.md").read(),
    long_description_content_type="text/markdown",
    author="puzzleYOU GmbH",
    url="https://github.com/puzzleYOU/parviraptor",
    python_requires=">=3.12",
    license="MIT",
    packages=find_packages("."),
    install_requires=[
        "Django>=4",
    ],
    classifiers=[
        "Development Status :: 5 - Production/Stable",
        "Environment :: Web Environment",
        "Framework :: Django",
        "Framework :: Django :: 4.2",
        "Framework :: Django :: 5.0",
        "Framework :: Django :: 5.1",
        "Framework :: Django :: 5.2",
        "Framework :: Django :: 6.0",
        "Intended Audience :: Developers",
        "License :: OSI Approved :: BSD License",
        "Operating System :: OS Independent",
        "Programming Language :: Python",
        "Programming Language :: Python :: 3 :: Only",
        "Programming Language :: Python :: 3.12",
        "Programming Language :: Python :: 3.13",
        "Programming Language :: Python :: 3.14",
        "Topic :: Software Development",
        "Topic :: Software Development :: Libraries",
    ],
    zip_safe=True,
)
