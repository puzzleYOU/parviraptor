===========
parviraptor
===========

parviraptor ist eine Django-App für die Verwaltung von Queues und Jobs.

- `AbstractJob` (in `parviraptor.models.abstract`) ist eine Basisklasse
  für Jobs, die von parviraptor verwaltet werden.

  - Apps, die parviraptor verwenden, können konkrete Job-Klassen von
    dieser Basisklasse ableiten. Auf diesem konkreten Job können für
    diesen Job spezifische, weitere Model-Felder definiert werden.

  - Von `AbstractJob` abgeleitete Klassen müssen `process()` implementieren.
    Diese Methode beinhaltet die Verarbeitungslogik des Jobs. Sollte es bei
    der Job-Verarbeitung zu einem Fehler kommen, muss in `process()` selbst
    ein entsprechender Rollback-Mechanismus implementiert werden.

- `parviraptor` implementiert zudem den Management-Command `process_queue`.

  - Dieser ist dafür zuständig, die notwendigen Zustandsübergänge der
    Jobs einzuleiten, z. B. dass konkret ein Job den Status `PROCESSING`
    erhält, sobald `process()` aufgerufen wurde, oder dass er auf `FAILED`
    übergeht, sollte es innerhalb von `process()` zu einer `Exception`
    gekommen sein.

  - Das Starten der Queue-Verarbeitung kann beispielsweise über die
    Shell per `./manage.py process_queue very_busy_app HeavyDutyJob`
    erfolgen.

    Die allgemeine "Syntax" lautet
    `./manage.py process_queue <app_label> <model>`.

- `monitor_queue_entries()` (in `parviraptor.monitoring`) ist dafür
  zuständig, ein Job-Model (oder mehrere) auf fehlgeschlagene und
  potentiell hängengebliebene Jobs zu untersuchen. Diese Funktion
  kann bspw. in einem Management-Command aufgerufen werden und
  entsprechende Log-Einträge schreiben, eine Mail auslösen usw.

- `enumerate_job_models()` (in `parviraptor.utils`) listet alle nicht-
  abstrakten Job-Models zu der übergebenen Django-`AppConfig` auf.
  Ein Anwendungsfall dafür wäre, alle Job-Models einer Django-App
  zu ermitteln, um diese an `monitor_queue_entries()` weiterzureichen.

Hinweise zur Entwicklung
========================

Tests
-----

`devtools/run-tests` ist dafür zuständig, die Testumgebung aufzusetzen,
führt die Unittests aus und prüft die Coding Conventions (`flake8`, `isort`).
Um die Unittests auszuführen, bedarf es lediglich einer Umgebung, in der
`docker` und `docker-compose` installiert sind.

Upgrades
--------

`devtools/upgrade-requirements` aktualisiert die `requirements.txt` im
Wurzelverzeichnis des Repositories. Voraussetzung hierfür ist lediglich
die Installation von `docker`.
