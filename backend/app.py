import hashlib
import json
import threading
import time
import uuid
from datetime import datetime, timedelta

from flask import Flask, jsonify, request, send_from_directory
from flask_cors import CORS

from config import CORS_ORIGIN, STATS_CACHE_TTL, PAGEVIEW_BATCH_SIZE
from models import SessionLocal, Record, PageView, init_db

app = Flask(__name__, static_folder="../frontend", static_url_path="")
CORS(app, origins=CORS_ORIGIN)

# ── In-memory cache ──────────────────────────────────────────────────
_stats_cache = {"data": None, "expires": 0}
_stats_lock = threading.Lock()

# ── Pageview batch buffer ────────────────────────────────────────────
_pv_buffer = []
_pv_lock = threading.Lock()


def _hash_ip(ip: str) -> str:
    return hashlib.sha256(ip.encode()).hexdigest()[:16]


def _flush_pageviews():
    global _pv_buffer
    with _pv_lock:
        if not _pv_buffer:
            return
        batch = _pv_buffer[:]
        _pv_buffer = []
    db = SessionLocal()
    try:
        db.bulk_save_objects(batch)
        db.commit()
    except Exception:
        db.rollback()
    finally:
        db.close()


# ── API Routes ───────────────────────────────────────────────────────

@app.route("/")
def index():
    resp = send_from_directory(app.static_folder, "index.html")
    resp.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    return resp


@app.route("/api/submit", methods=["POST"])
def submit():
    data = request.get_json(silent=True)
    if not data or "answers" not in data or "result_code" not in data:
        return jsonify({"error": "bad request"}), 400

    record_id = uuid.uuid4().hex[:12]
    ip_hash = _hash_ip(request.remote_addr or "unknown")

    db = SessionLocal()
    try:
        record = Record(
            id=record_id,
            answers=json.dumps(data["answers"]),
            result_code=data["result_code"],
            result_name=data.get("result_name", ""),
            ip_hash=ip_hash,
            user_agent=(request.headers.get("User-Agent") or "")[:256],
        )
        db.add(record)
        db.commit()

        total = db.query(Record).count()
        same_type = db.query(Record).filter(Record.result_code == data["result_code"]).count()
        pct = round(same_type / total * 100, 1) if total > 0 else 0

        # Invalidate stats cache so next stats call is fresh
        with _stats_lock:
            _stats_cache["expires"] = 0

        return jsonify({
            "id": record_id,
            "stats": {"total": total, "same_type": same_type, "percentage": f"{pct}%"},
        })
    except Exception as e:
        db.rollback()
        return jsonify({"error": str(e)}), 500
    finally:
        db.close()


@app.route("/api/stats", methods=["GET"])
def stats():
    now = time.time()
    with _stats_lock:
        if _stats_cache["data"] and now < _stats_cache["expires"]:
            resp = jsonify(_stats_cache["data"])
            resp.headers["Cache-Control"] = f"public, max-age={STATS_CACHE_TTL}"
            return resp

    db = SessionLocal()
    try:
        total = db.query(Record).count()
        rows = db.query(Record.result_code, db.query(Record).filter(Record.result_code == Record.result_code).correlate(Record).count()).all()
        # Simpler approach: get distribution
        from sqlalchemy import func as sqlfunc
        dist_rows = db.query(Record.result_code, sqlfunc.count(Record.id)).group_by(Record.result_code).all()
        distribution = {row[0]: row[1] for row in dist_rows}

        data = {"total": total, "distribution": distribution}
        with _stats_lock:
            _stats_cache["data"] = data
            _stats_cache["expires"] = now + STATS_CACHE_TTL

        resp = jsonify(data)
        resp.headers["Cache-Control"] = f"public, max-age={STATS_CACHE_TTL}"
        return resp
    except Exception as e:
        return jsonify({"total": 0, "distribution": {}}), 200
    finally:
        db.close()


@app.route("/api/pageview", methods=["POST"])
def pageview():
    data = request.get_json(silent=True)
    if not data:
        return jsonify({"ok": True})

    pv = PageView(
        page=data.get("page", "unknown"),
        referrer=data.get("referrer", ""),
        ip_hash=_hash_ip(request.remote_addr or "unknown"),
        user_agent=(request.headers.get("User-Agent") or "")[:256],
    )
    with _pv_lock:
        _pv_buffer.append(pv)
        should_flush = len(_pv_buffer) >= PAGEVIEW_BATCH_SIZE

    if should_flush:
        _flush_pageviews()
    else:
        # Also flush on a timer (don't lose data)
        threading.Timer(10.0, _flush_pageviews).start()

    return jsonify({"ok": True})


@app.route("/api/analytics", methods=["GET"])
def analytics():
    db = SessionLocal()
    try:
        from sqlalchemy import func as sqlfunc
        now = datetime.utcnow()
        today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)

        daily_pv = db.query(PageView).filter(PageView.created_at >= today_start).count()
        daily_uv = db.query(sqlfunc.count(sqlfunc.distinct(PageView.ip_hash))).filter(
            PageView.created_at >= today_start
        ).scalar() or 0

        return jsonify({"daily_uv": daily_uv, "daily_pv": daily_pv})
    except Exception:
        return jsonify({"daily_uv": 0, "daily_pv": 0})
    finally:
        db.close()


# ── Init & Run ───────────────────────────────────────────────────────

init_db()

if __name__ == "__main__":
    app.run(debug=True, port=5000)
