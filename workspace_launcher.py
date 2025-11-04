"""Unified launcher for the PowWash backend and Flutter workspace."""
from __future__ import annotations

import argparse
import shutil
import subprocess
import threading
import time
import json
from pathlib import Path
from typing import Iterable, List, Optional

from werkzeug.serving import make_server

from twilio_app import app as twilio_flask_app
from workspace_settings import load_workspace_settings


class FlaskServer:
    """Run the Twilio Flask app in a background thread."""

    def __init__(self, host: str, port: int) -> None:
        self._host = host
        self._port = port
        self._server = make_server(host, port, twilio_flask_app)
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)

    @property
    def url(self) -> str:
        return f"http://{self._host}:{self._port}"

    def start(self) -> None:
        print(f"[server] Starting Twilio webhook + REST API on {self.url}")
        self._thread.start()
        print(f"[server] API root available at {self.url}/")

    def stop(self) -> None:
        print("[server] Shutting down Flask server …")
        self._server.shutdown()
        self._thread.join(timeout=5)


class FlutterRunner:
    """Launch the Flutter workspace as a subprocess."""

    def __init__(
        self,
        project_dir: Path,
        *,
        device_id: Optional[str],
        base_url: str,
        skip_pub_get: bool,
        extra_args: Iterable[str],
    ) -> None:
        self._project_dir = project_dir
        self._device_id = device_id
        self._base_url = base_url
        self._skip_pub_get = skip_pub_get
        self._extra_args = list(extra_args)
        self._process: Optional[subprocess.Popen[str]] = None
        self._output_thread: Optional[threading.Thread] = None

    @staticmethod
    def _ensure_flutter_available() -> None:
        if shutil.which("flutter") is None:
            raise RuntimeError(
                "Flutter SDK not detected on PATH. Install Flutter 3.19+ and rerun the launcher."
            )

    def _run_pub_get(self) -> None:
        if self._skip_pub_get:
            return

        print("[flutter] Running `flutter pub get` …")
        result = subprocess.run(
            ["flutter", "pub", "get"],
            cwd=self._project_dir,
            check=False,
        )
        if result.returncode != 0:
            raise RuntimeError("`flutter pub get` failed. Inspect the output above for details.")

    def _auto_detect_device(self) -> Optional[str]:
        """Try to automatically select a preferred Flutter device (chrome > macos)."""
        try:
            result = subprocess.run(
                ["flutter", "devices", "--machine"],
                capture_output=True,
                text=True,
                check=True,
            )
            devices = json.loads(result.stdout)
            device_ids = [d["id"] for d in devices]
            if "chrome" in device_ids:
                return "chrome"
            if "macos" in device_ids:
                return "macos"
        except Exception:
            pass
        return None

    def start(self) -> None:
        self._ensure_flutter_available()
        self._run_pub_get()

        # Choose device: explicit > auto-detect > none
        device = self._device_id or self._auto_detect_device()
        command: List[str] = ["flutter", "run", f"--dart-define=API_BASE_URL={self._base_url}"]
        if device:
            command.extend(["-d", device])
        command.extend(self._extra_args)

        print("[flutter] Launching workspace with command:")
        print(f"[flutter]   {' '.join(command)}")

        self._process = subprocess.Popen(
            command,
            cwd=self._project_dir,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
        )

        assert self._process.stdout is not None  # for mypy/static type checkers
        self._output_thread = threading.Thread(
            target=self._stream_output, args=(self._process.stdout,), daemon=True
        )
        self._output_thread.start()

    def _stream_output(self, stream: Iterable[str]) -> None:
        for line in stream:
            print(f"[flutter] {line.rstrip()}")

    def is_running(self) -> bool:
        return self._process is not None and self._process.poll() is None

    def stop(self) -> None:
        if not self._process:
            return

        print("[flutter] Sending quit command …")
        try:
            if self._process.stdin:
                self._process.stdin.write("q\n")
                self._process.stdin.flush()
        except Exception:
            pass

        try:
            self._process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            print("[flutter] Forcing process termination …")
            self._process.terminate()
            try:
                self._process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self._process.kill()

        if self._output_thread:
            self._output_thread.join(timeout=2)


class WorkspaceLauncher:
    """Coordinate the Flask server and optional Flutter client."""

    def __init__(
        self,
        host: str,
        port: int,
        *,
        launch_flutter: bool,
        flutter_device: Optional[str],
        flutter_base_url: str,
        skip_pub_get: bool,
        flutter_extra_args: Iterable[str],
    ) -> None:
        self._server = FlaskServer(host, port)
        self._flutter_runner = (
            FlutterRunner(
                Path("flutter_app"),
                device_id=flutter_device,
                base_url=flutter_base_url,
                skip_pub_get=skip_pub_get,
                extra_args=list(flutter_extra_args),
            )
            if launch_flutter
            else None
        )

    def start(self) -> None:
        self._server.start()
        if self._flutter_runner:
            try:
                self._flutter_runner.start()
            except Exception:
                self._server.stop()
                raise

    def run_forever(self) -> None:
        try:
            while True:
                if self._flutter_runner and not self._flutter_runner.is_running():
                    print("[launcher] Flutter process exited — shutting down server.")
                    break
                time.sleep(0.5)
        except KeyboardInterrupt:
            print("\n[launcher] Caught Ctrl+C, shutting down …")
        finally:
            self.stop()

    def stop(self) -> None:
        if self._flutter_runner:
            self._flutter_runner.stop()
        self._server.stop()


def parse_args(argv: Optional[List[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Run the Twilio Flask webhook and, optionally, the Flutter workspace in one command."
        )
    )
    parser.add_argument("--host", default="0.0.0.0", help="Host interface for the Flask server.")
    parser.add_argument("--port", type=int, default=5002, help="Port for the Flask server.")
    parser.add_argument(
        "--no-flutter",
        action="store_true",
        help="Skip launching the Flutter client (useful when running on CI or without the SDK).",
    )
    parser.add_argument(
        "--flutter-device",
        help="Optional Flutter device ID (pass the value from `flutter devices`).",
    )
    parser.add_argument(
        "--flutter-base-url",
        help="Override the API base URL passed to Flutter (defaults to 127.0.0.1 on the chosen port).",
    )
    parser.add_argument(
        "--skip-pub-get",
        action="store_true",
        help="Do not run `flutter pub get` before launching the workspace.",
    )
    parser.add_argument(
        "--flutter-extra-args",
        nargs=argparse.REMAINDER,
        default=(),
        help=(
            "Additional arguments forwarded to `flutter run`. Prefix with `--` to ensure the launcher stops parsing."
        ),
    )
    return parser.parse_args(argv)


def main(argv: Optional[List[str]] = None) -> int:
    args = parse_args(argv)
    settings = load_workspace_settings()
    default_base_url = settings.api.base_url or f"http://127.0.0.1:{args.port}"
    base_url = args.flutter_base_url or default_base_url

    launcher = WorkspaceLauncher(
        args.host,
        args.port,
        launch_flutter=not args.no_flutter,
        flutter_device=args.flutter_device,
        flutter_base_url=base_url,
        skip_pub_get=args.skip_pub_get,
        flutter_extra_args=args.flutter_extra_args,
    )

    launcher.start()
    launcher.run_forever()
    return 0


if __name__ == "__main__":  # pragma: no cover - CLI entry point
    raise SystemExit(main())
