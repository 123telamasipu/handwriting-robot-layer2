from __future__ import annotations

import json
import tempfile
import threading
import unittest
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

from src.handwriting_robot_layer2_wl_handwriting import (
    CaptureSubmission,
    load_target_charset,
)
from src.handwriting_robot_layer2_wl_handwriting.mobile_server import (
    MobileCollectorService,
    create_server,
)


def capture_document(
    character: str = "的", status: str = "complete"
) -> dict:
    return {
        "schema_version": "1.0",
        "writer_id": "mobile_test",
        "writer_name": "脱敏测试用户",
        "character": character,
        "variant": 1,
        "status": status,
        "client": {
            "application": "mobile_web",
            "user_agent": "test-agent",
            "viewport": {
                "width_px": 390,
                "height_px": 844,
                "device_pixel_ratio": 3,
            },
            "pointer_types": ["touch"],
        },
        "strokes": [
            {
                "points": [
                    {
                        "x": -0.1,
                        "y": 0.2,
                        "t_ms": 0,
                        "pressure": 0.4,
                        "source": "touch",
                    },
                    {
                        "x": 1.1,
                        "y": 0.8,
                        "t_ms": 20,
                        "pressure": 0.7,
                        "source": "touch",
                    },
                ]
            }
        ],
    }


class CaptureProtocolTests(unittest.TestCase):
    def test_submission_normalizes_browser_points(self) -> None:
        submission = CaptureSubmission.from_dict(capture_document())
        points = submission.buffer.strokes[0].points

        self.assertEqual(0.0, points[0].x)
        self.assertEqual(1.0, points[1].x)
        self.assertEqual("touch", points[0].source)
        self.assertEqual(["touch"], submission.capture_context["pointer_types"])
        self.assertEqual(
            390, submission.capture_context["viewport"]["width_px"]
        )

    def test_submission_rejects_non_finite_points(self) -> None:
        document = capture_document()
        document["strokes"][0]["points"][0]["x"] = float("nan")

        with self.assertRaisesRegex(ValueError, "point.x must be finite"):
            CaptureSubmission.from_dict(document)


class MobileCollectorServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.data_dir = Path(self.temporary.name)
        self.service = MobileCollectorService(load_target_charset(), self.data_dir)

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def test_service_saves_and_recovers_mobile_sample(self) -> None:
        result = self.service.save(capture_document())
        recovered = self.service.sample("mobile_test", "的", 1)

        self.assertEqual("complete", result["state"])
        self.assertEqual(1, result["progress"]["completed"])
        self.assertEqual("complete", recovered["state"])
        self.assertEqual(
            ["touch"], recovered["sample"]["input_sources"]
        )
        self.assertEqual(
            "mobile_web",
            recovered["sample"]["capture_context"]["application"],
        )


class MobileCollectorHttpTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        service = MobileCollectorService(
            load_target_charset(), Path(self.temporary.name)
        )
        self.server = create_server("127.0.0.1", 0, service, "123456")
        self.thread = threading.Thread(
            target=self.server.serve_forever, name="mobile-test-server", daemon=True
        )
        self.thread.start()
        self.base_url = f"http://127.0.0.1:{self.server.server_address[1]}"

    def tearDown(self) -> None:
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)
        self.temporary.cleanup()

    def request_json(
        self,
        path: str,
        method: str = "GET",
        body: dict | None = None,
    ) -> dict:
        data = None if body is None else json.dumps(body).encode("utf-8")
        request = urllib.request.Request(
            f"{self.base_url}{path}",
            data=data,
            method=method,
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(request, timeout=5) as response:
            return json.loads(response.read().decode("utf-8"))

    def test_http_requires_access_token(self) -> None:
        with self.assertRaises(urllib.error.HTTPError) as context:
            urllib.request.urlopen(f"{self.base_url}/api/health", timeout=5)
        self.assertEqual(403, context.exception.code)

    def test_http_round_trip_and_static_app(self) -> None:
        with urllib.request.urlopen(
            f"{self.base_url}/?token=123456", timeout=5
        ) as response:
            html = response.read().decode("utf-8")
        config = self.request_json("/api/config?token=123456")
        saved = self.request_json(
            "/api/sample?token=123456",
            method="POST",
            body=capture_document(),
        )
        query = urllib.parse.urlencode(
            {
                "token": "123456",
                "writer_id": "mobile_test",
                "character": "的",
                "variant": 1,
            }
        )
        recovered = self.request_json(f"/api/sample?{query}")

        self.assertIn("手机笔迹采集", html)
        self.assertEqual(1140, len(config["entries"]))
        self.assertEqual("complete", saved["state"])
        self.assertEqual("complete", recovered["state"])


if __name__ == "__main__":
    unittest.main()
