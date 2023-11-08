===========
parviraptor
===========

`parviraptor` ist eine Django-App, die Queues und Jobs verwaltet.

Sie stellt Basisklassen bereit, um per Django-Models Jobs - und ihre
Abhängigkeiten untereinander, falls es welche gibt - zu modellieren.

Teil der Django-App ist außerdem ein Management-Command, der dafür zuständig
ist, eine konkrete Queue zu verarbeiten.

Kompatiblitätshinweise
----------------------

`parviraptor` ist in jedem Django-Projekt lauffähig. Unterstützt und
getestet werden die Django-Versionen 3.2, 4.0, 4.1 und 4.2 mit jeweils
MySQL 5 und MySQL 8, wo Django es jeweils unterstützt.

Ausführen der Tests
-------------------

Die Tests werden per `just test` ausgeführt. Das Prüfen gegen die festgelegten
Coding Conventions erfolgt im Zuge der Tests, kann aber auch separat per
`just lint` ausgeführt werden.

Entwicklungsnotizen
-------------------

Voraussetzungen für die Entwicklung an `parviraptor` ist eine systemweite
Installation von `nix` 2.x und `direnv` 2.x auf einem Unix-Hostsystem.
`nix` muss den "Nix-Command" und Flake-Support aktiviert haben.

Die Shell für die `parviraptor`-Entwicklungsumgebung kann z. B. über
`direnv exec . bash` (`bash` kann durch jede beliebige Shell ersetzt werden)
gestartet werden. Beim ersten Mal muss man vorher `direnv allow` ausführen.
Shorthand-Befehle innerhalb der Shell werden per `just --help` gezeigt und
erklärt.

Um `parviraptor` in anderen Projekten zu verwenden, muss man (wie für Django-
Projekte üblich), 'parviraptor' in das `INSTALLED_APPS`-Setting des einbindenden
Projekts eintragen.

Grobanleitung "wie bindet man parviraptor ein?"
-----------------------------------------------

- `parviraptor.models.AbstractJobFactory` generiert Basisklassen für Jobs,
  die von parviraptor verwaltet werden.
  Näheres ist ihrer Klassendokumentation zu entnehmen.
  Für ein Beispiel für abgeleitete Jobs mit und ohne Abhängigkeiten
  siehe `tests/models.py`.

- parviraptor implementiert die Endpunkte `/queue-monitoring` und
  `/open-queue-entries`. Diese können z. B. wie folgt in die
  URL-Patterns des einbindenden Django-Projekts eingebunden werden::

    from django.urls import include, path
    urlpatterns = [
        path("", include("parviraptor.urls")),
    ]

  Der Monitoring-Endpunkt liefert im Gutfall "Alles OK" oder listet
  fehlgeschlagene, hängengebliebene oder lange unverarbeitete Jobs auf.
  `/open-queue-entries` liefert eine menschenlesbare tabellarische
  Darstellung von Jobs aus, die offen oder in Arbeit sind.

- `./manage.py process_queue` startet einen Worker für eine konkrete Queue.
  Intern leitet diese alle notwendigen Zustandsübergänge ein (z. B. von
  `PROCESSING` zu `PROCESSED`/`FAILED`) und startet bei temporären Fehlern
  mit der Backoff-Rechenvorschrift `2 ^ min(x, 5)` Jobs neu, solange der
  entsprechende Grenzwert nicht erreicht wurde.
  Allgemeiner Aufruf: `./manage.py process_queue <app_label> <model>`.
  Beispielaufruf: `./manage.py process_queue very_busy_app HeavyDutyJob`

- `./manage_py clean_old_processed_jobs` kann genutzt werden, um alte
  erfolgreich verarbeitete Jobs aufzuräumen.

- Um abgeleitete parviraptor-basierte Queues in Unittests zu testen, kann die
  Funktion `make_test_case_for_all_queues` benutzt werden. Diese generiert
  automatisch einen Test für alle Queues in der aktuellen Django-Installation.
  Man muss sich lediglich darum bemühen, eine `JobEntryFactory` abzuleiten und
  diese so auszuimplementieren, dass für jede existierende Queue Jobs angelegt
  werden, die der Test dann verarbeiten kann. Beide Symbole finden sich in dem
  Modul `parviraptor.test`; nähere Details sind ihren Docstrings zu entnehmen.
