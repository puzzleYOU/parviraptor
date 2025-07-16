# parviraptor

`parviraptor` is a Django app for managing queue-based jobs, both
sequentially and in parallel.

This package provides

- abstract base classes and factories for modelling Django Model based
  job queues

- capabilities of supporting jobs' interdependencies

- a management command for processing job queues

- rudimentary Django views for monitoring and job queue statistics


## Compatibility

`parviraptor` should be compatible with any Django codebase. The test suite
covers Django 3.2, 4.0, 4.1 and 4.2 with each MySQL 5 and 8, the latter
depending on which MySQL versions Django supports.

## Running tests

Tests and lints are covered by `just test`, you can separately lint using
the command `just lint`.

## Development

For developing `parviraptor` it is necessary to have `nix` 2.x and `direnv`
2.x installed as system-wide dependencies. `nix` must have enabled the features
"nix command" and "flake support".

The development shell can be invoked by e.g. `direnv exec . zsh`. Executing
this for the first time might require to run `direnv allow`. Shorthand
commands, for example those mentioned in chapter "Running tests", can be
enumerated using `just --help`.

In order to test whether the package would be built correctly, you can
run `python setup.py build` in the development shell to inspect whether
`build/lib/parviraptor/` looks as expected.

## Installation

Just add `'parviraptor'` to your `INSTALLED_APPS` Django setting as usual.

## API outline

- `parviraptor.models.AbstractJobFactory` is a factory generating
  job base classes. For details, see the class documentation itself.
  Also, you can spy into `tests/models.py` to see job class examples
  which have (or don't have) interdependencies.

- `parviraptor` implements rudimentary views for monitoring
  (`/queue-monitoring`) and statistics (`/open-queue-entries`).
  You can reuse them by including the URLs by e.g.

  ```python
    from django.urls import include, path
    urlpatterns = [
        # ...
        path("", include("parviraptor.urls")),
        # ...
    ]
  ```

  - `/queue-monitoring`: As a german IT department started implementing
    this functionality this endpoint serves "Alles OK" in case everything
    is fine. If there are failed, long unprocessed or long pending jobs,
    they are counted per queue and written down in english plain text.

  - `/open-queue-entries` serves a human-readable, styled table (in English)
    with open or pending job counts.

- The management command `process_queue` starts a worker for processing a
  certain job queue. It internally manages each necessary job transition
  (e.g. `PROCESSING` -> `FAILED`). `parviraptor` supports so-called temporary
  job failures, i.e. if a "temporary exception" is raised, `parviraptor`
  resumes the job respecting the per-job configurable backoff strategy.
  - generic call: `./manage.py process_queue <app_label> <model>`.
  - example: `./manage.py process_queue very_busy_app HeavyDutyJob`

- The management command `clean_old_processed_jobs` can be used for cleaning
  up stale job entries.

- `parviraptor.test` provides a simple API for testing job queues.
  `parviraptor.test.make_test_case_for_all_queues` infers a test class which
  automatically covers all queues in your current codebase. You just need
  to derive from `JobEntryFactory` and provide an implementation which covers
  creating concrete instances for each job class.
  For further details, see according class and function documentations.
