from __future__ import annotations

from pathlib import Path

from flask import Flask, send_from_directory

BASE_DIR = Path(__file__).resolve().parent
FLUTTER_BUILD_DIR = (BASE_DIR.parent / 'flutter_whatsapp_clone' / 'build' / 'web').resolve()

app = Flask(
    __name__,
    static_folder=str(FLUTTER_BUILD_DIR),
    static_url_path='/',
)


@app.get('/')
def index() -> object:
    """Serve the Flutter entry point."""
    return send_from_directory(FLUTTER_BUILD_DIR, 'index.html')


@app.get('/<path:resource>')
def assets(resource: str) -> object:
    """Serve Flutter's generated assets and fall back to index for routes."""
    target = FLUTTER_BUILD_DIR / resource
    if target.exists():
        return send_from_directory(FLUTTER_BUILD_DIR, resource)
    return send_from_directory(FLUTTER_BUILD_DIR, 'index.html')


if __name__ == '__main__':
    if not FLUTTER_BUILD_DIR.exists():
        raise SystemExit(
            'Flutter build assets were not found. Run "flutter build web" inside '
            'flutter_whatsapp_clone before launching the Flask server.'
        )

    app.run(host='0.0.0.0', port=5000, debug=True)
