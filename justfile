help:
    just --list

# Set up a python-venv for e.g. comfortable editor autocompletion support.
setup-virtual-environment:
    python -m venv ./.venv
    .venv/bin/pip install .

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
    just tox-env unittests-dj60-mysql97-py314 -- {{ARGS}}

# Checks all coding conventions
lint:
    ruff check parviraptor/ tests/
    ruff format --check parviraptor/ tests/
    mypy parviraptor/

# Runs ruff import sorting
isort *ARGS='':
    ruff check --select I --fix parviraptor/ tests/ {{ARGS}}

# Formats code with ruff
format *ARGS='':
    ruff format parviraptor/ tests/ {{ARGS}}

ctags:
    ctags -R parviraptor/ tests/

grep PATTERN:
    grep -R {{PATTERN}} \
        --exclude-dir=.venv \
        --exclude-dir=.direnv \
        --exclude-dir=.tox \
        --exclude-dir=build \
        --exclude=tags
