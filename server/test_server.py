import io
import tempfile
import unittest
from pathlib import Path

from PIL import Image
from server import create_app


def png_file():
    stream = io.BytesIO()
    Image.new("RGB", (32, 32), "white").save(stream, format="PNG")
    stream.seek(0)
    return stream


class ServerFlowTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.calls = 0

        def detector(_image):
            self.calls += 1
            return ["dump_truck"] if self.calls == 1 else ["dump_truck", "dump_truck", "excavator"]

        self.app = create_app(detector, Path(self.temp.name) / "test.db")
        self.client = self.app.test_client()

    def tearDown(self):
        self.temp.cleanup()

    def test_complete_flow_and_history(self):
        payload = {
            "taskName": "Вывоз грунта",
            "startTime": "11:00",
            "items": [{"type": "dump_truck", "quantity": 2}],
        }
        response = self.client.put("/plans/2026-09-18", json=payload)
        self.assertEqual(response.status_code, 200)

        first = self.client.post(
            "/observations",
            data={"date": "2026-09-18", "time": "12:00", "file": (png_file(), "one.png")},
            content_type="multipart/form-data",
        )
        self.assertEqual(first.status_code, 201)
        self.assertFalse(first.json["isComplete"])
        self.assertEqual(first.json["comparison"][0]["missing"], 1)

        second = self.client.post(
            "/observations",
            data={"date": "2026-09-18", "time": "14:00", "file": (png_file(), "two.png")},
            content_type="multipart/form-data",
        )
        self.assertEqual(second.status_code, 201)
        self.assertFalse(second.json["isComplete"])  # unexpected excavator also warns
        self.assertEqual(len(second.json["observations"]), 2)
        self.assertEqual(second.json["latestObservation"]["counts"]["dump_truck"], 2)

    def test_plan_update_keeps_observations(self):
        payload = {"taskName": "Задача", "startTime": "09:00", "items": [{"type": "excavator", "quantity": 1}]}
        self.client.put("/plans/2026-09-19", json=payload)
        self.client.post(
            "/observations",
            data={"date": "2026-09-19", "time": "10:00", "file": (png_file(), "photo.png")},
            content_type="multipart/form-data",
        )
        payload["items"] = [{"type": "excavator", "quantity": 3}]
        self.client.put("/plans/2026-09-19", json=payload)
        report = self.client.get("/reports/2026-09-19")
        self.assertEqual(len(report.json["observations"]), 1)
        self.assertEqual(report.json["comparison"][0]["planned"], 3)

    def test_validation(self):
        bad = self.client.put("/plans/not-a-date", json={})
        self.assertEqual(bad.status_code, 400)
        no_plan = self.client.post(
            "/observations",
            data={"date": "2026-09-20", "time": "10:00", "file": (png_file(), "photo.png")},
            content_type="multipart/form-data",
        )
        self.assertEqual(no_plan.status_code, 404)


if __name__ == "__main__":
    unittest.main()
