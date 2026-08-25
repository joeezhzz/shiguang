"""拾光 · 看板本地服务（Flask，仅本机访问）"""
import os
import sys

from flask import Flask, jsonify, request, send_from_directory

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from storage import db


def create_app():
    app = Flask(__name__, static_folder="static", static_url_path="/static")

    @app.route("/")
    def index():
        return app.send_static_file("index.html")

    @app.route("/api/cards")
    def api_list():
        args = {k: request.args.get(k) for k in ("topic", "priority", "status", "period") if request.args.get(k)}
        q = request.args.get("q")
        return jsonify(db.list_cards(q=q, **args))

    @app.route("/media/<path:filename>")
    def media(filename):
        return send_from_directory(db.MEDIA_DIR, filename)

    @app.route("/api/cards/<int:cid>", methods=["PATCH"])
    def api_update(cid):
        data = request.get_json(force=True, silent=True) or {}
        ok = db.update_card(cid, **data)
        return jsonify({"ok": ok, "card": db.get_card(cid)})

    @app.route("/api/cards/<int:cid>", methods=["DELETE"])
    def api_delete(cid):
        db.delete_card(cid)
        return jsonify({"ok": True})

    return app


if __name__ == "__main__":
    create_app().run(host="127.0.0.1", port=8765, debug=True)
