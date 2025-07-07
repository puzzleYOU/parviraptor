from xml.etree import ElementTree as ET

from django.test import TestCase

from .models import DummyJob, IncrementCounterJob


class OpenQueueEntriesTests(TestCase):
    def parse_records(self):
        resp = self.client.get("/open-queue-entries/")
        self.assertEqual(200, resp.status_code)

        content = resp.content.decode()
        table = ET.fromstring(content).find("body/table")
        rows = table.findall("tr")

        # die erste Tabellenzeile sind die Überschriften
        self.assertEqual({"th"}, {el.tag for el in rows[0]})

        return {(row[0].text, row[1].text) for row in rows[1:]}

    def test_empty_queues(self):
        self.assertEqual(
            {
                ("DummyJob", "0"),
                ("DummyProductJob", "0"),
                ("IncrementCounterJob", "0"),
            },
            self.parse_records(),
        )

    def test_shows_open_and_processing_queue_entries(self):
        DummyJob.objects.create(a=1, b=2)
        self.assertEqual(
            {
                ("DummyJob", "1"),
                ("DummyProductJob", "0"),
                ("IncrementCounterJob", "0"),
            },
            self.parse_records(),
        )
        DummyJob.objects.create(a=1, b=2)
        self.assertEqual(
            {
                ("DummyJob", "2"),
                ("DummyProductJob", "0"),
                ("IncrementCounterJob", "0"),
            },
            self.parse_records(),
        )
        DummyJob.objects.create(a=1, b=2, status="PROCESSING")
        self.assertEqual(
            {
                ("DummyJob", "3"),
                ("DummyProductJob", "0"),
                ("IncrementCounterJob", "0"),
            },
            self.parse_records(),
        )
        DummyJob.objects.create(a=1, b=2, status="PROCESSED")
        self.assertEqual(
            {
                ("DummyJob", "3"),
                ("DummyProductJob", "0"),
                ("IncrementCounterJob", "0"),
            },
            self.parse_records(),
        )
        IncrementCounterJob.objects.create(counter_id="irrelevant")
        self.assertEqual(
            {
                ("DummyJob", "3"),
                ("DummyProductJob", "0"),
                ("IncrementCounterJob", "1"),
            },
            self.parse_records(),
        )
