import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from flask import Flask, jsonify, request
from werkzeug.exceptions import HTTPException

from app.csv_store import CsvStore


def create_app(csv_path=None, **store_options):
    app = Flask(__name__, static_folder=str(ROOT / "static"), static_url_path="/static")
    store = CsvStore(csv_path or ROOT / "input" / "04_natural.csv", **store_options)
    app.extensions["csv_store"] = store

    @app.get("/")
    def index():
        return app.send_static_file("index.html")

    @app.get("/api/items")
    def items():
        return jsonify(store.items())

    @app.get("/api/items/<instance_id>")
    def detail(instance_id):
        return jsonify(store.detail(instance_id))

    @app.put("/api/items/<instance_id>/review")
    def review(instance_id):
        item = store.update(instance_id, request.get_json())
        return jsonify(item=item, saved=True)

    @app.get("/api/progress")
    def progress():
        return jsonify(store.progress())

    @app.errorhandler(KeyError)
    def not_found(error):
        return jsonify(error="指定された文が見つかりません"), 404

    @app.errorhandler(ValueError)
    def invalid(error):
        return jsonify(error=str(error)), 400

    @app.errorhandler(OSError)
    def storage_error(error):
        app.logger.exception("CSV save failed")
        return jsonify(error="CSVを保存できませんでした。ファイルの権限や空き容量を確認し、再試行してください。"), 500

    @app.errorhandler(HTTPException)
    def http_error(error):
        return jsonify(error=error.description), error.code

    return app


if __name__ == "__main__":
    create_app(backup_count=int(os.getenv("BACKUP_COUNT", "10")),
               backup_interval=float(os.getenv("BACKUP_INTERVAL_SECONDS", "300"))).run(
                   host="127.0.0.1", port=5000, debug=False)
