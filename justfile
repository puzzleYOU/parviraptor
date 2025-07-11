help:
    just --list

# Set up a python-venv for e.g. comfortable editor autocompletion support.
setup-virtual-environment:
    python -m venv ./.venv
    source .venv/bin/activate
    .venv/bin/pip install setuptools
    .venv/bin/python setup.py install

# Executes all tests
test:
    just lint
    just tox

# Run tox tests, optionally against a specific environment (e.g. just tox run -e unittests-dj40-mysql8).
tox *ARGS='':
    devtools/run-tests {{ARGS}}

# Runs tests against a certain tox environment (e.g. unittests-dj40-mysql8)
tox-env *ARGS='':
    just tox run -e {{ARGS}}

# Runs a single unittest
tox-unittest *ARGS='':
    just tox-env unittests-dj42-mysql8 -- {{ARGS}}

# Checks all coding conventions
lint:
    python -m flake8 parviraptor/ tests/
    just isort --check-only --diff
    just black --check

# Runs isort against each source directory
isort *ARGS='':
    python -m isort parviraptor/ tests/ {{ARGS}}

# Runs black against each source directory
black *ARGS='':
    black \
      --line-length 80 \
      --target-version py312 \
      parviraptor \
      tests \
      {{ARGS}}

ctags:
    ctags -R parviraptor/ tests/

grep PATTERN:
    grep -R {{PATTERN}} \
        --exclude-dir=.venv \
        --exclude-dir=.direnv \
        --exclude-dir=.tox \
        --exclude-dir=build \
        --exclude=tags
