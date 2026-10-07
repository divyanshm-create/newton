# SPDX-FileCopyrightText: Copyright (c) 2026 The Newton Developers
# SPDX-License-Identifier: Apache-2.0

import importlib.util
import socket
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from urllib.parse import urlsplit

# ruff: noqa: PLC0415


def available_port():
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        return listener.getsockname()[1]


@unittest.skipUnless(importlib.util.find_spec("rerun"), "Requires the optional rerun-sdk package")
class TestViewerRerunRecording(unittest.TestCase):
    def test_recording_keeps_data_with_viewer_connection(self):
        """Read logged data from disk after configuring each viewer connection mode."""
        import rerun as rr

        from newton.viewer import ViewerRerun

        for mode in ("remote", "native", "web", "notebook"):
            with self.subTest(mode=mode), tempfile.TemporaryDirectory() as directory:
                recording_path = Path(directory) / "simulation.rrd"
                server = rr.RecordingStream("newton-recording-test-server")
                uri = rr.serve_grpc(grpc_port=available_port(), recording=server)
                kwargs = {"record_to_rrd": str(recording_path), "keep_historical_data": True}
                if mode == "remote":
                    kwargs["address"] = uri
                elif mode == "native":
                    kwargs.update(serve_web_viewer=False, grpc_port=urlsplit(uri).port)
                elif mode == "web":
                    kwargs["grpc_port"] = available_port()
                viewer = None
                try:
                    with (
                        patch("newton._src.viewer.viewer_rerun.is_jupyter_notebook", return_value=mode == "notebook"),
                        patch.object(rr, "serve_web_viewer"),
                        patch.object(
                            rr,
                            "spawn",
                            side_effect=lambda *, port, connect=True, address=uri: (
                                rr.connect_grpc(address) if connect else None
                            ),
                        ),
                    ):
                        viewer = ViewerRerun(**kwargs)
                        viewer.begin_frame(0.5)
                        viewer.log_scalar("recording_probe", 42.0)
                        viewer.end_frame()
                        viewer.close()
                        viewer = None
                    completed = subprocess.run(
                        [sys.executable, "-m", "rerun", "rrd", "print", str(recording_path)],
                        capture_output=True,
                        text=True,
                        timeout=30,
                        check=True,
                    )
                    self.assertIn("recording_probe", completed.stdout)
                    self.assertIn("Scalars", completed.stdout)
                finally:
                    if viewer is not None:
                        viewer.close()
                    server.disconnect()


if __name__ == "__main__":
    unittest.main(verbosity=2)
