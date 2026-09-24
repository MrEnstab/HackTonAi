import tempfile
import unittest
from pathlib import Path
from server import create_app

PAYLOAD = {"taskName": "Вывоз грунта", "stage": "Земляные работы", "zone": "Котлован А", "startTime": "09:00", "items": [{"type": "excavator", "quantity": 2}]}

class HistoryTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.db = Path(self.temp.name) / 'test.db'
        self.client = create_app(lambda image: ['excavator', 'dump_truck'], self.db).test_client()

    def tearDown(self):
        self.temp.cleanup()

    def test_project_scoped_daily_plans_persist(self):
        response = self.client.post('/projects', json={'name': 'Объект А'})
        self.assertEqual(response.status_code, 201)
        project = response.json['project']['id']
        other = self.client.post('/projects', json={'name': 'Объект Б'}).json['project']['id']
        for day in ['2026-09-18', '2026-09-19']:
            self.assertEqual(self.client.put(f'/projects/{project}/plans/{day}', json=PAYLOAD).status_code, 200)
        self.assertEqual(self.client.put(f'/projects/{other}/plans/2026-09-18', json=PAYLOAD).status_code, 200)
        reopened = create_app(lambda image: [], self.db).test_client()
        plans = reopened.get(f'/projects/{project}/plans').json['plans']
        self.assertEqual(len(plans), 2)
        self.assertEqual(plans[0]['zone'], 'Котлован А')
        self.assertEqual(len(reopened.get(f'/projects/{other}/plans').json['plans']), 1)

    def test_dated_photos_snapshot_evidence_and_chronological_report(self):
        from test_server import png_file
        project = self.client.post('/projects', json={'name': 'Фото'}).json['project']['id']
        url = f'/projects/{project}'
        for day in ['2026-09-18', '2026-09-19']:
            self.client.put(f'{url}/plans/{day}', json=PAYLOAD)
        empty = self.client.get(f'{url}/report')
        self.assertEqual(empty.status_code, 200)
        self.assertIsNone(empty.json['latestObservation'])
        self.assertEqual(empty.json['observations'], [])
        for timestamp in ['2026-09-19T15:47', '2026-09-18T09:13']:
            response = self.client.post(f'{url}/observations', data={'observedAt': timestamp, 'file': (png_file(), '../../unsafe.png')})
            self.assertEqual(response.status_code, 201)
        modified = dict(PAYLOAD, items=[{'type': 'excavator', 'quantity': 9}])
        self.client.put(f'{url}/plans/2026-09-18', json=modified)
        report = create_app(lambda image: [], self.db).test_client().get(f'{url}/report').json
        self.assertEqual([o['observedAt'] for o in report['observations']], ['2026-09-18T09:13:00+03:00', '2026-09-19T15:47:00+03:00'])
        first = report['observations'][0]
        self.assertEqual(first['planned']['excavator'], 2)
        self.assertEqual(first['counts']['mobile_crane'], 0)
        self.assertEqual(first['total'], 2)
        self.assertEqual({w['kind'] for w in first['warnings']}, {'missing', 'unexpected'})
        self.assertEqual(first['planSnapshot']['zone'], 'Котлован А')
        evidence = self.client.get(first['evidenceUrl'])
        self.assertEqual(evidence.status_code, 200)
        self.assertEqual(evidence.mimetype, 'image/jpeg')
        evidence.close()
        other = self.client.post('/projects', json={'name': 'Другой'}).json['project']['id']
        self.assertEqual(self.client.get(f'/projects/{other}/report').json['observations'], [])

    def test_legacy_migration_backs_up_and_preserves_history_once(self):
        import sqlite3
        from server import _init_database
        legacy = Path(self.temp.name) / 'legacy.db'
        _init_database(legacy)
        with sqlite3.connect(legacy) as db:
            db.execute("INSERT INTO plans(plan_date,task_name,start_time) VALUES ('2026-09-18','Старый план','09:00')")
            db.execute("INSERT INTO plan_items VALUES (1,'excavator',2)")
            db.execute("INSERT INTO observations(plan_id,observed_at,source_filename,total) VALUES (1,'2026-09-18T10:00:00','old.png',1)")
            db.execute("INSERT INTO observation_counts VALUES (1,'excavator',1)")
        db.close()
        client = create_app(lambda image: [], legacy).test_client()
        projects = client.get('/projects').json['projects']
        self.assertEqual(len(projects), 1)
        report = client.get(f"/projects/{projects[0]['id']}/report").json
        self.assertEqual(len(report['observations']), 1)
        self.assertIsNone(report['observations'][0]['evidenceUrl'])
        self.assertEqual(report['observations'][0]['snapshotProvenance'], 'legacy_plan_at_migration')
        backups = list(legacy.parent.glob('legacy.db.pre-projects-*.bak'))
        self.assertEqual(len(backups), 1)
        with sqlite3.connect(backups[0]) as backup:
            self.assertEqual(backup.execute('SELECT count(*) FROM observations').fetchone()[0], 1)
        backup.close()
        reopened = create_app(lambda image: [], legacy).test_client()
        self.assertEqual(len(reopened.get('/projects').json['projects']), 1)
        self.assertEqual(len(reopened.get(f"/projects/{projects[0]['id']}/report").json['observations']), 1)
        self.assertEqual(len(list(legacy.parent.glob('legacy.db.pre-projects-*.bak'))), 1)

if __name__ == '__main__':
    unittest.main()
