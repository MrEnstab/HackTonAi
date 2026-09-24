"""Project-scoped durable history; legacy tables remain available for migration."""
import json
import sqlite3
from contextlib import closing


def backup_before_migration(database_path):
    if not database_path.exists():
        return
    with closing(sqlite3.connect(database_path)) as source:
        if source.execute('PRAGMA user_version').fetchone()[0] >= 2:
            return
        backup = database_path.with_name(database_path.name + '.pre-projects-' + datetime.now().strftime('%Y%m%d-%H%M%S-%f') + '.bak')
        with closing(sqlite3.connect(backup)) as destination:
            source.backup(destination)

import re
from collections import Counter
from datetime import datetime
from uuid import uuid4
from pathlib import Path
from flask import jsonify, request, send_from_directory


def comparison_for(planned, counts, labels):
    rows, warnings = [], []
    for kind, label in labels.items():
        required, actual = planned.get(kind, 0), counts.get(kind, 0)
        if not required and not actual:
            continue
        missing = max(required - actual, 0)
        unexpected = actual if not required else 0
        rows.append(dict(type=kind, label=label, planned=required, actual=actual,
                         missing=missing, unexpected=unexpected, complete=not missing))
        if missing:
            warnings.append(dict(kind='missing', type=kind, quantity=missing,
                                 message=f'{label}: не обнаружено на снимке {missing} из {required}.'))
        if unexpected:
            warnings.append(dict(kind='unexpected', type=kind, quantity=unexpected,
                                 message=f'{label}: тип не предусмотрен этапом ({actual}).'))
    return rows, warnings



def install_history(app, database_path, detector, detector_lock, connect, validate_date, validate_plan, labels, read_image):
    with connect(database_path) as db:
        db.executescript('''
        CREATE TABLE IF NOT EXISTS projects (
            id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL,
            created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')));
        CREATE TABLE IF NOT EXISTS daily_plans (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            project_id INTEGER NOT NULL REFERENCES projects(id),
            plan_date TEXT NOT NULL, payload TEXT NOT NULL,
            updated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
            UNIQUE(project_id, plan_date));
        CREATE TABLE IF NOT EXISTS photo_checks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            project_id INTEGER NOT NULL REFERENCES projects(id),
            plan_id INTEGER NOT NULL REFERENCES daily_plans(id),
            observed_at TEXT NOT NULL, source_filename TEXT NOT NULL,
            evidence_name TEXT, result TEXT NOT NULL,
            created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')));
        CREATE TABLE IF NOT EXISTS history_meta (key TEXT PRIMARY KEY, value INTEGER NOT NULL);
        CREATE INDEX IF NOT EXISTS checks_chronological ON photo_checks(project_id,observed_at,id);
        ''')
        if db.execute('PRAGMA user_version').fetchone()[0] < 2:
            old_plans = db.execute('SELECT * FROM plans ORDER BY id').fetchall()
            if old_plans:
                project_id = db.execute("INSERT INTO projects(name) VALUES ('Импортированные планы')").lastrowid
                db.execute("INSERT INTO history_meta VALUES ('legacy_project',?)", (project_id,))
                for old in old_plans:
                    items = [dict(type=item['equipment_type'], label=labels[item['equipment_type']], quantity=item['quantity']) for item in db.execute('SELECT * FROM plan_items WHERE plan_id=?', (old['id'],))]
                    payload = dict(taskName=old['task_name'], startTime=old['start_time'], stage=old['task_name'], zone='', items=items)
                    plan_id = db.execute('INSERT INTO daily_plans(project_id,plan_date,payload,updated_at) VALUES (?,?,?,?)', (project_id, old['plan_date'], json.dumps(payload, ensure_ascii=False), old['updated_at'])).lastrowid
                    snapshot = dict(payload, id=plan_id, projectId=project_id, date=old['plan_date'], updatedAt=old['updated_at'])
                    planned = {item['type']: item['quantity'] for item in items}
                    for observation in db.execute('SELECT * FROM observations WHERE plan_id=?', (old['id'],)).fetchall():
                        raw = {item['equipment_type']: item['quantity'] for item in db.execute('SELECT * FROM observation_counts WHERE observation_id=?', (observation['id'],))}
                        counts = {kind: raw.get(kind, 0) for kind in labels}
                        comparison, warnings = comparison_for(planned, counts, labels)
                        result = dict(counts=counts, total=observation['total'], planned=planned, planSnapshot=snapshot, comparison=comparison, warnings=warnings, isComplete=not warnings, snapshotProvenance='legacy_plan_at_migration')
                        db.execute('INSERT INTO photo_checks(project_id,plan_id,observed_at,source_filename,result,created_at) VALUES (?,?,?,?,?,?)', (project_id, plan_id, observation['observed_at'] + '+03:00', observation['source_filename'], json.dumps(result, ensure_ascii=False), observation['created_at']))
            db.execute('PRAGMA user_version = 2')

    def project_exists(db, project_id):
        return db.execute('SELECT id FROM projects WHERE id=?', (project_id,)).fetchone() is not None

    def plan_json(row):
        return dict(json.loads(row['payload']), id=row['id'], projectId=row['project_id'], date=row['plan_date'], updatedAt=row['updated_at'])

    @app.get('/projects')
    def projects():
        with connect(database_path) as db:
            return jsonify(projects=[dict(row) for row in db.execute('SELECT * FROM projects ORDER BY id')])

    @app.post('/projects')
    def new_project():
        payload = request.get_json(silent=True)
        name = payload.get('name') if isinstance(payload, dict) else None
        if not isinstance(name, str) or not name.strip() or len(name.strip()) > 120:
            return jsonify(error='Название проекта: от 1 до 120 символов.'), 400
        with connect(database_path) as db:
            cursor = db.execute('INSERT INTO projects(name) VALUES (?)', (name.strip(),))
            row = db.execute('SELECT * FROM projects WHERE id=?', (cursor.lastrowid,)).fetchone()
        return jsonify(project=dict(row)), 201

    @app.get('/projects/<int:project_id>/plans')
    def project_plans(project_id):
        with connect(database_path) as db:
            if not project_exists(db, project_id):
                return jsonify(error='Проект не найден.'), 404
            rows = db.execute('SELECT * FROM daily_plans WHERE project_id=? ORDER BY plan_date', (project_id,)).fetchall()
            return jsonify(plans=[plan_json(row) for row in rows])

    @app.route('/projects/<int:project_id>/plans/<plan_date>', methods=['GET', 'PUT'])
    def daily_plan(project_id, plan_date):
        try:
            validate_date(plan_date)
            if request.method == 'PUT':
                payload = request.get_json(silent=True)
                task, start, items = validate_plan(payload)
                stage, zone = payload.get('stage', task), payload.get('zone', '')
                if not isinstance(stage, str) or not stage.strip() or len(stage) > 120 or not isinstance(zone, str) or len(zone) > 120:
                    raise ValueError('Укажите этап и зону длиной до 120 символов.')
                payload = dict(taskName=task, startTime=start, stage=stage.strip(), zone=zone.strip(), items=[dict(type=kind, label=labels[kind], quantity=n) for kind, n in items])
        except ValueError as exc:
            return jsonify(error=str(exc)), 400
        with connect(database_path) as db:
            if not project_exists(db, project_id):
                return jsonify(error='Проект не найден.'), 404
            if request.method == 'PUT':
                db.execute("INSERT INTO daily_plans(project_id,plan_date,payload) VALUES (?,?,?) ON CONFLICT(project_id,plan_date) DO UPDATE SET payload=excluded.payload,updated_at=strftime('%Y-%m-%dT%H:%M:%fZ','now')", (project_id, plan_date, json.dumps(payload, ensure_ascii=False)))
            row = db.execute('SELECT * FROM daily_plans WHERE project_id=? AND plan_date=?', (project_id, plan_date)).fetchone()
            if row is None:
                return jsonify(error='На эту дату план не создан.'), 404
            return jsonify(plan=plan_json(row))

    evidence_dir = database_path.parent / (database_path.stem + '_evidence')

    def check_json(row):
        return dict(json.loads(row['result']), id=row['id'], projectId=row['project_id'],
                    observedAt=row['observed_at'], sourceFilename=row['source_filename'],
                    createdAt=row['created_at'],
                    evidenceUrl=f"/evidence/{row['evidence_name']}" if row['evidence_name'] else None)

    def report_data(project_id):
        with connect(database_path) as db:
            project = db.execute('SELECT * FROM projects WHERE id=?', (project_id,)).fetchone()
            if project is None:
                return None
            rows = db.execute('SELECT * FROM photo_checks WHERE project_id=? ORDER BY observed_at,id', (project_id,)).fetchall()
            observations = [check_json(row) for row in rows]
            plans = [plan_json(row) for row in db.execute('SELECT * FROM daily_plans WHERE project_id=? ORDER BY plan_date', (project_id,))]
            return dict(project=dict(project), plans=plans, observations=observations,
                        latestObservation=observations[-1] if observations else None,
                        timezone='Europe/Moscow', timezoneLabel='МСК (UTC+03:00)')

    @app.get('/projects/<int:project_id>/report')
    def project_report(project_id):
        data = report_data(project_id)
        return jsonify(data) if data else (jsonify(error='Проект не найден.'), 404)

    @app.get('/evidence/<name>')
    def evidence(name):
        if re.fullmatch(r'[0-9a-f]{32}\.jpg', name) is None:
            return jsonify(error='Фото не найдено.'), 404
        with connect(database_path) as db:
            if db.execute('SELECT id FROM photo_checks WHERE evidence_name=?', (name,)).fetchone() is None:
                return jsonify(error='Фото не найдено.'), 404
        return send_from_directory(evidence_dir.resolve(), name, mimetype='image/jpeg')

    @app.post('/projects/<int:project_id>/observations')
    def project_observation(project_id):
        try:
            timestamp = request.form.get('observedAt', '')
            if re.fullmatch(r'\d{4}-\d{2}-\d{2}T\d{2}:\d{2}', timestamp) is None:
                raise ValueError('Дата и время снимка: YYYY-MM-DDTHH:MM, МСК (UTC+03:00).')
            datetime.strptime(timestamp, '%Y-%m-%dT%H:%M')
        except ValueError as exc:
            return jsonify(error=str(exc)), 400
        with connect(database_path) as db:
            row = db.execute('SELECT * FROM daily_plans WHERE project_id=? AND plan_date=?', (project_id, timestamp[:10])).fetchone()
            if row is None:
                return jsonify(error='Сначала создайте план этого проекта на дату снимка.'), 404
            snapshot = plan_json(row)
        try:
            image, filename = read_image()
            with detector_lock:
                raw = Counter(detector(image))
            counts = {kind: raw.get(kind, 0) for kind in labels}
        except ValueError as exc:
            return jsonify(error=str(exc)), 400
        except Exception:
            app.logger.exception('Model inference failed')
            return jsonify(error='Ошибка распознавания. Проверка не сохранена.'), 500
        planned = {item['type']: item['quantity'] for item in snapshot['items']}
        comparison, warnings = comparison_for(planned, counts, labels)
        result = dict(counts=counts, total=sum(counts.values()), planned=planned,
                      planSnapshot=snapshot, comparison=comparison, warnings=warnings,
                      isComplete=not warnings, snapshotProvenance='captured_at_upload')
        evidence_dir.mkdir(parents=True, exist_ok=True)
        name = uuid4().hex + '.jpg'
        destination = evidence_dir / name
        try:
            image.save(destination, format='JPEG', quality=92)
            with connect(database_path) as db:
                cursor = db.execute('INSERT INTO photo_checks(project_id,plan_id,observed_at,source_filename,evidence_name,result) VALUES (?,?,?,?,?,?)',
                    (project_id, row['id'], timestamp + ':00+03:00', filename.replace('\\\\', '/').split('/')[-1][:255], name, json.dumps(result, ensure_ascii=False)))
                saved_id = cursor.lastrowid
        except Exception:
            destination.unlink(missing_ok=True)
            app.logger.exception('Could not persist photo check')
            return jsonify(error='Не удалось сохранить проверку.'), 500
        data = report_data(project_id)
        data['savedObservationId'] = saved_id
        return jsonify(data), 201
