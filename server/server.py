"""Local equipment planning and photo-recognition HTTP API."""

import argparse
import os
import re
import sqlite3
import warnings
from collections import Counter
from datetime import date
from pathlib import Path
from threading import Lock

from flask import Flask, jsonify, request
from PIL import Image, ImageOps, UnidentifiedImageError
from werkzeug.exceptions import HTTPException

ROOT = Path(__file__).resolve().parent
os.environ.setdefault("YOLO_CONFIG_DIR", str(ROOT / ".yolo"))
Image.MAX_IMAGE_PIXELS = 20_000_000

EQUIPMENT_TYPES = (
    "excavator",
    "dump_truck",
    "wheel_loader",
    "motor_grader",
    "concrete_mixer",
    "mobile_crane",
)
EQUIPMENT_LABELS = {
    "excavator": "Экскаватор",
    "dump_truck": "Самосвал",
    "wheel_loader": "Фронтальный погрузчик",
    "motor_grader": "Автогрейдер",
    "concrete_mixer": "Автобетоносмеситель",
    "mobile_crane": "Автомобильный кран",
}
TIME_PATTERN = re.compile(r"^(?:[01]\d|2[0-3]):[0-5]\d$")


def _validate_date(value):
    if not isinstance(value, str):
        raise ValueError("Дата должна быть в формате YYYY-MM-DD.")
    try:
        parsed = date.fromisoformat(value)
    except ValueError as exc:
        raise ValueError("Дата должна быть в формате YYYY-MM-DD.") from exc
    if parsed.isoformat() != value:
        raise ValueError("Дата должна быть в формате YYYY-MM-DD.")
    return value


def _validate_time(value):
    if not isinstance(value, str) or TIME_PATTERN.fullmatch(value) is None:
        raise ValueError("Время должно быть в формате HH:MM.")
    return value


from contextlib import contextmanager


@contextmanager
def _connect(database_path):
    connection = sqlite3.connect(str(database_path), timeout=10)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    try:
        with connection:
            yield connection
    finally:
        connection.close()


def _init_database(database_path):
    database_path.parent.mkdir(parents=True, exist_ok=True)
    with _connect(database_path) as connection:
        connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS plans (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                plan_date TEXT NOT NULL UNIQUE,
                task_name TEXT NOT NULL,
                start_time TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
                updated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
            );
            CREATE TABLE IF NOT EXISTS plan_items (
                plan_id INTEGER NOT NULL REFERENCES plans(id) ON DELETE CASCADE,
                equipment_type TEXT NOT NULL,
                quantity INTEGER NOT NULL CHECK(quantity > 0),
                PRIMARY KEY (plan_id, equipment_type)
            );
            CREATE TABLE IF NOT EXISTS observations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                plan_id INTEGER NOT NULL REFERENCES plans(id) ON DELETE CASCADE,
                observed_at TEXT NOT NULL,
                source_filename TEXT NOT NULL,
                total INTEGER NOT NULL,
                created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
            );
            CREATE TABLE IF NOT EXISTS observation_counts (
                observation_id INTEGER NOT NULL REFERENCES observations(id) ON DELETE CASCADE,
                equipment_type TEXT NOT NULL,
                quantity INTEGER NOT NULL CHECK(quantity >= 0),
                PRIMARY KEY (observation_id, equipment_type)
            );
            """
        )


def _validate_plan_payload(payload):
    if not isinstance(payload, dict):
        raise ValueError("Ожидается JSON-объект.")
    task_name = str(payload.get("taskName", "")).strip()
    if not task_name or len(task_name) > 120:
        raise ValueError("Название задачи обязательно и должно быть не длиннее 120 символов.")
    start_time = _validate_time(payload.get("startTime"))
    raw_items = payload.get("items")
    if not isinstance(raw_items, list) or not raw_items:
        raise ValueError("Добавьте хотя бы один вид техники.")
    items = []
    seen = set()
    for raw in raw_items:
        if not isinstance(raw, dict):
            raise ValueError("Некорректная строка техники.")
        equipment_type = raw.get("type")
        quantity = raw.get("quantity")
        if equipment_type not in EQUIPMENT_TYPES:
            raise ValueError("Выбран неподдерживаемый вид техники.")
        if equipment_type in seen:
            raise ValueError("Один вид техники нельзя добавлять дважды.")
        if isinstance(quantity, bool) or not isinstance(quantity, int) or not 1 <= quantity <= 999:
            raise ValueError("Количество должно быть целым числом от 1 до 999.")
        seen.add(equipment_type)
        items.append((equipment_type, quantity))
    return task_name, start_time, items


def _read_image():
    upload = request.files.get("file")
    if upload is None or not upload.filename:
        raise ValueError("Выберите JPG- или PNG-файл.")
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(upload.stream) as source:
                if source.format not in {"JPEG", "PNG"}:
                    raise ValueError("Поддерживаются только JPG и PNG.")
                image = ImageOps.exif_transpose(source).convert("RGB")
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError, Image.DecompressionBombWarning) as exc:
        raise ValueError("Файл повреждён или изображение превышает 20 мегапикселей.") from exc
    return image, upload.filename


def _serialize_plan(connection, row):
    item_rows = connection.execute(
        "SELECT equipment_type, quantity FROM plan_items WHERE plan_id = ? ORDER BY equipment_type",
        (row["id"],),
    ).fetchall()
    return {
        "id": row["id"],
        "date": row["plan_date"],
        "taskName": row["task_name"],
        "startTime": row["start_time"],
        "items": [
            {"type": item["equipment_type"], "label": EQUIPMENT_LABELS[item["equipment_type"]], "quantity": item["quantity"]}
            for item in item_rows
        ],
        "createdAt": row["created_at"],
        "updatedAt": row["updated_at"],
    }


def _load_report(database_path, plan_date):
    with _connect(database_path) as connection:
        row = connection.execute("SELECT * FROM plans WHERE plan_date = ?", (plan_date,)).fetchone()
        if row is None:
            return None
        plan = _serialize_plan(connection, row)
        observation_rows = connection.execute(
            "SELECT * FROM observations WHERE plan_id = ? ORDER BY observed_at ASC, id ASC",
            (row["id"],),
        ).fetchall()
        observations = []
        for observation in observation_rows:
            count_rows = connection.execute(
                "SELECT equipment_type, quantity FROM observation_counts WHERE observation_id = ?",
                (observation["id"],),
            ).fetchall()
            counts = {item["equipment_type"]: item["quantity"] for item in count_rows}
            observations.append({
                "id": observation["id"],
                "observedAt": observation["observed_at"],
                "time": observation["observed_at"][11:16],
                "sourceFilename": observation["source_filename"],
                "counts": counts,
                "total": observation["total"],
            })
        latest_counts = observations[-1]["counts"] if observations else {}
        planned = {item["type"]: item["quantity"] for item in plan["items"]}
        comparison = []
        for equipment_type in EQUIPMENT_TYPES:
            plan_count = planned.get(equipment_type, 0)
            actual_count = latest_counts.get(equipment_type, 0)
            if plan_count or actual_count:
                comparison.append({
                    "type": equipment_type,
                    "label": EQUIPMENT_LABELS[equipment_type],
                    "planned": plan_count,
                    "actual": actual_count,
                    "missing": max(plan_count - actual_count, 0),
                    "unexpected": actual_count if not plan_count else 0,
                    "complete": actual_count >= plan_count and not (actual_count if not plan_count else 0),
                })
        is_complete = bool(observations) and all(
            item["missing"] == 0 and item["unexpected"] == 0 for item in comparison
        )
        return {
            "plan": plan,
            "observations": observations,
            "latestObservation": observations[-1] if observations else None,
            "comparison": comparison,
            "isComplete": is_complete,
        }


def create_app(detector, database_path=ROOT / "equipment.db"):
    database_path = Path(database_path)
    from history import backup_before_migration
    backup_before_migration(database_path)
    _init_database(database_path)
    app = Flask(__name__)
    app.json.ensure_ascii = False
    app.config["MAX_CONTENT_LENGTH"] = 10 * 1024 * 1024
    detector_lock = Lock()

    @app.errorhandler(HTTPException)
    def http_error(error):
        return jsonify(error=error.description), error.code

    @app.get("/health")
    def health():
        return jsonify(status="ok")

    @app.get("/equipment")
    def equipment():
        return jsonify(equipment=[{"type": key, "label": EQUIPMENT_LABELS[key]} for key in EQUIPMENT_TYPES])

    @app.get("/plans")
    def list_plans():
        with _connect(database_path) as connection:
            rows = connection.execute(
                """SELECT p.*, COALESCE(SUM(pi.quantity), 0) AS total_planned,
                          COUNT(pi.equipment_type) AS item_count
                   FROM plans p LEFT JOIN plan_items pi ON pi.plan_id = p.id
                   GROUP BY p.id ORDER BY p.plan_date ASC"""
            ).fetchall()
        return jsonify(plans=[{
            "id": row["id"], "date": row["plan_date"], "taskName": row["task_name"],
            "startTime": row["start_time"], "totalPlanned": row["total_planned"],
            "itemCount": row["item_count"], "updatedAt": row["updated_at"],
        } for row in rows])

    @app.get("/plans/<plan_date>")
    def get_plan(plan_date):
        try:
            _validate_date(plan_date)
        except ValueError as exc:
            return jsonify(error=str(exc)), 400
        with _connect(database_path) as connection:
            row = connection.execute("SELECT * FROM plans WHERE plan_date = ?", (plan_date,)).fetchone()
            if row is None:
                return jsonify(error="На эту дату план не создан."), 404
            plan = _serialize_plan(connection, row)
        return jsonify(plan=plan)

    @app.put("/plans/<plan_date>")
    def put_plan(plan_date):
        try:
            _validate_date(plan_date)
            task_name, start_time, items = _validate_plan_payload(request.get_json(silent=True))
        except ValueError as exc:
            return jsonify(error=str(exc)), 400
        with _connect(database_path) as connection:
            row = connection.execute("SELECT id FROM plans WHERE plan_date = ?", (plan_date,)).fetchone()
            if row is None:
                cursor = connection.execute(
                    "INSERT INTO plans(plan_date, task_name, start_time) VALUES (?, ?, ?)",
                    (plan_date, task_name, start_time),
                )
                plan_id = cursor.lastrowid
            else:
                plan_id = row["id"]
                connection.execute(
                    "UPDATE plans SET task_name = ?, start_time = ?, updated_at = strftime('%Y-%m-%dT%H:%M:%fZ', 'now') WHERE id = ?",
                    (task_name, start_time, plan_id),
                )
                connection.execute("DELETE FROM plan_items WHERE plan_id = ?", (plan_id,))
            connection.executemany(
                "INSERT INTO plan_items(plan_id, equipment_type, quantity) VALUES (?, ?, ?)",
                [(plan_id, equipment_type, quantity) for equipment_type, quantity in items],
            )
            plan_row = connection.execute("SELECT * FROM plans WHERE id = ?", (plan_id,)).fetchone()
            plan = _serialize_plan(connection, plan_row)
        return jsonify(plan=plan)

    @app.get("/reports/<plan_date>")
    def report(plan_date):
        try:
            _validate_date(plan_date)
        except ValueError as exc:
            return jsonify(error=str(exc)), 400
        data = _load_report(database_path, plan_date)
        if data is None:
            return jsonify(error="На эту дату план не создан."), 404
        return jsonify(data)

    @app.post("/detect")
    def detect():
        try:
            image, _ = _read_image()
            with detector_lock:
                counts = dict(Counter(detector(image)))
        except ValueError as exc:
            return jsonify(error=str(exc)), 400
        except Exception:
            app.logger.exception("Model inference failed")
            return jsonify(error="Ошибка распознавания. Подробности в журнале сервера."), 500
        counts = {key: value for key, value in counts.items() if key in EQUIPMENT_TYPES}
        return jsonify(counts=counts, total=sum(counts.values()))

    @app.post("/observations")
    def create_observation():
        try:
            plan_date = _validate_date(request.form.get("date"))
            observed_time = _validate_time(request.form.get("time"))
        except ValueError as exc:
            return jsonify(error=str(exc)), 400
        with _connect(database_path) as connection:
            plan_row = connection.execute("SELECT id FROM plans WHERE plan_date = ?", (plan_date,)).fetchone()
        if plan_row is None:
            return jsonify(error="Сначала создайте план на выбранную дату."), 404
        try:
            image, filename = _read_image()
            with detector_lock:
                raw_counts = dict(Counter(detector(image)))
            counts = {key: value for key, value in raw_counts.items() if key in EQUIPMENT_TYPES and value > 0}
        except ValueError as exc:
            return jsonify(error=str(exc)), 400
        except Exception:
            app.logger.exception("Model inference failed")
            return jsonify(error="Ошибка распознавания. Подробности в журнале сервера."), 500
        observed_at = f"{plan_date}T{observed_time}:00"
        with _connect(database_path) as connection:
            cursor = connection.execute(
                "INSERT INTO observations(plan_id, observed_at, source_filename, total) VALUES (?, ?, ?, ?)",
                (plan_row["id"], observed_at, filename, sum(counts.values())),
            )
            observation_id = cursor.lastrowid
            connection.executemany(
                "INSERT INTO observation_counts(observation_id, equipment_type, quantity) VALUES (?, ?, ?)",
                [(observation_id, equipment_type, quantity) for equipment_type, quantity in counts.items()],
            )
        data = _load_report(database_path, plan_date)
        data["savedObservationId"] = observation_id
        return jsonify(data), 201

    from history import install_history
    install_history(app, database_path, detector, detector_lock, _connect, _validate_date,
                    _validate_plan_payload, EQUIPMENT_LABELS, _read_image)
    return app


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--weights", type=Path, default=ROOT / "best.pt")
    parser.add_argument("--database", type=Path, default=ROOT / "equipment.db")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--device", default="cpu", help="cpu или 0 для NVIDIA GPU")
    parser.add_argument("--conf", type=float, default=0.25)
    args = parser.parse_args()
    if not args.weights.is_file():
        parser.error(f"Файл весов не найден: {args.weights}")
    if not 0 < args.conf < 1 or not 1 <= args.port <= 65535:
        parser.error("Требуется 0 < conf < 1 и 1 <= port <= 65535.")
    from ultralytics import YOLO
    from waitress import serve
    from dataset_tools import normalise_names
    model = YOLO(str(args.weights.resolve()))
    names = normalise_names(model.names)
    if names != list(EQUIPMENT_TYPES):
        parser.error("Классы модели не совпадают с HANDOFF.md. Ожидаются: " + ", ".join(EQUIPMENT_TYPES))

    def detector(image):
        result = model.predict(image, conf=args.conf, device=args.device, verbose=False)[0]
        return [names[int(class_id)] for class_id in result.boxes.cls.tolist()]

    detector(Image.new("RGB", (64, 64)))
    print(f"Weights: {args.weights.resolve()}", flush=True)
    print(f"Database: {args.database.resolve()}", flush=True)
    print(f"API ready: http://127.0.0.1:{args.port}", flush=True)
    serve(create_app(detector, args.database), host="127.0.0.1", port=args.port, threads=2, max_request_body_size=10 * 1024 * 1024)


if __name__ == "__main__":
    main()
