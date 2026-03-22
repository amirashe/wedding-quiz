from flask import Flask, render_template, request, jsonify
from flask_socketio import SocketIO, emit
import sqlite3
import secrets
import random
import os

from questions import QUESTIONS

app = Flask(__name__)
app.secret_key = secrets.token_hex(32)
socketio = SocketIO(app, cors_allowed_origins="*", async_mode="threading")

DATABASE = os.path.join(os.path.dirname(__file__), "wedding.db")


# ── DB helpers ──────────────────────────────────────────────────────────────

def get_db():
    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    with get_db() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS players (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                name            TEXT    NOT NULL,
                token           TEXT    UNIQUE NOT NULL,
                score           INTEGER DEFAULT 0,
                current_question INTEGER DEFAULT 0,
                finished        INTEGER DEFAULT 0,
                created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        conn.commit()


def leaderboard_data(conn):
    rows = conn.execute("""
        SELECT name, score, finished
        FROM players
        ORDER BY score DESC, created_at ASC
        LIMIT 10
    """).fetchall()
    return [
        {"name": r["name"], "score": r["score"], "finished": bool(r["finished"])}
        for r in rows
    ]


def get_question_order(token):
    """Deterministic shuffle of question indices based on player token."""
    rng = random.Random(token)
    indices = list(range(len(QUESTIONS)))
    rng.shuffle(indices)
    return indices


def question_payload(position, token):
    """Return question at position (in player's shuffled order), with shuffled options."""
    real_idx = get_question_order(token)[position]
    q = QUESTIONS[real_idx]

    # Shuffle options deterministically per player+position
    rng = random.Random(token + str(position))
    option_order = list(range(len(q["options"])))
    rng.shuffle(option_order)

    shuffled_options = [q["options"][i] for i in option_order]
    new_correct = option_order.index(q["correct"])

    return {
        "index":   position,
        "text":    q["question"],
        "options": shuffled_options,
        "total":   len(QUESTIONS),
        "_correct": new_correct,   # used server-side only
    }


def get_correct_index(position, token):
    """Recalculate correct answer index for a given position and token."""
    real_idx = get_question_order(token)[position]
    q = QUESTIONS[real_idx]
    rng = random.Random(token + str(position))
    option_order = list(range(len(q["options"])))
    rng.shuffle(option_order)
    return option_order.index(q["correct"])


# ── Routes ───────────────────────────────────────────────────────────────────

@app.route("/")
def index():
    return render_template("index.html", total_questions=len(QUESTIONS))


@app.route("/admin")
def admin():
    return render_template("admin.html")


@app.route("/api/start", methods=["POST"])
def start_game():
    data = request.get_json(silent=True) or {}
    name = (data.get("name") or "").strip()

    if not name:
        return jsonify({"error": "שם נדרש"}), 400
    if len(name) > 50:
        return jsonify({"error": "שם ארוך מדי"}), 400

    token = secrets.token_urlsafe(16)
    with get_db() as conn:
        conn.execute("INSERT INTO players (name, token) VALUES (?, ?)", (name, token))
        conn.commit()

    return jsonify({
        "token": token,
        "question": question_payload(0, token),
    })


@app.route("/api/answer", methods=["POST"])
def submit_answer():
    data = request.get_json(silent=True) or {}
    token = data.get("token")
    answer_index = data.get("answer_index")

    if token is None or answer_index is None:
        return jsonify({"error": "חסר מידע"}), 400

    with get_db() as conn:
        player = conn.execute(
            "SELECT * FROM players WHERE token = ?", (token,)
        ).fetchone()

        if not player:
            return jsonify({"error": "שחקן לא נמצא"}), 404

        if player["finished"]:
            return jsonify({"finished": True, "score": player["score"]})

        q_idx = player["current_question"]
        if q_idx >= len(QUESTIONS):
            return jsonify({"error": "אין שאלות"}), 400

        correct_idx = get_correct_index(q_idx, token)
        is_correct  = (int(answer_index) == correct_idx)
        new_score   = player["score"] + (10 if is_correct else 0)
        next_idx    = q_idx + 1
        finished    = 1 if next_idx >= len(QUESTIONS) else 0

        conn.execute(
            "UPDATE players SET score=?, current_question=?, finished=? WHERE token=?",
            (new_score, next_idx, finished, token),
        )
        conn.commit()

        response = {
            "correct":       is_correct,
            "correct_index": correct_idx,
            "score":         new_score,
            "finished":      bool(finished),
        }

        if not finished:
            response["question"] = question_payload(next_idx, token)
        else:
            board = leaderboard_data(conn)
            socketio.emit("leaderboard_update", board)
            response["leaderboard"] = board

        return jsonify(response)


@app.route("/api/resume", methods=["POST"])
def resume_game():
    data  = request.get_json(silent=True) or {}
    token = data.get("token")

    with get_db() as conn:
        player = conn.execute(
            "SELECT * FROM players WHERE token = ?", (token,)
        ).fetchone()

        if not player:
            return jsonify({"error": "not_found"}), 404

        response = {
            "name":             player["name"],
            "score":            player["score"],
            "finished":         bool(player["finished"]),
            "question_index":   player["current_question"],
            "total_questions":  len(QUESTIONS),
        }

        if player["finished"]:
            response["leaderboard"] = leaderboard_data(conn)
        else:
            q_idx = player["current_question"]
            if q_idx < len(QUESTIONS):
                response["question"] = question_payload(q_idx, token)

        return jsonify(response)


@app.route("/api/admin/reset", methods=["POST"])
def reset_scores():
    with get_db() as conn:
        conn.execute("DELETE FROM players")
        conn.commit()
    socketio.emit("leaderboard_update", [])
    return jsonify({"ok": True})


@app.route("/api/leaderboard")
def leaderboard_api():
    with get_db() as conn:
        return jsonify(leaderboard_data(conn))


# ── Socket.IO ────────────────────────────────────────────────────────────────

@socketio.on("connect")
def on_connect():
    with get_db() as conn:
        emit("leaderboard_update", leaderboard_data(conn))


@socketio.on("request_leaderboard")
def on_request_leaderboard():
    with get_db() as conn:
        emit("leaderboard_update", leaderboard_data(conn))


# ── Main ─────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    init_db()
    print("\n" + "=" * 52)
    print("  🎊  אפליקציית החתונה פועלת!")
    print("=" * 52)
    print(f"  ✅  {len(QUESTIONS)} שאלות נטענו")
    print("  🖥️   כתובת מקומית:  http://localhost:5000")
    print("  ⚙️   עמוד ניהול:     http://localhost:5000/admin")
    print()
    print("  📡  כדי שאורחים יוכלו לגשת מהטלפון:")
    print("      פתח טרמינל נוסף והרץ:")
    print("      ./venv/bin/ngrok http 5000")
    print("      (צריך ngrok מותקן - ראה README)")
    print("=" * 52 + "\n")
    port = int(os.environ.get("PORT", 5000))
    socketio.run(app, host="0.0.0.0", port=port, debug=False, allow_unsafe_werkzeug=True)
