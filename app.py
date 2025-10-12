from __future__ import annotations

from flask import Flask, render_template

app = Flask(__name__)


@app.get('/')
def index() -> str:
    """Render the chat workspace."""
    return render_template('index.html')


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
