import hashlib
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

import aos
import registry as R
import web


class WebPathsTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        for target, name, value in [
            (R, 'REGISTRY_DB', self.root / 'registry.db'),
            (aos, 'APPROVALS_DB', self.root / 'approvals.db'),
            (aos, 'BOARDS', self.root / 'boards'),
            (web, 'AOS_ENV', 'development'),
        ]:
            p = patch.object(target, name, value)
            p.start()
            self.addCleanup(p.stop)
        R.init_registry()
        aos.init_approvals()
        R.register('10', 'JD Writer', 'people', 'green', 'agent', 'Validate with supervisor.',
                   profile='test-profile', owners=[('owner', 'owner')])
        R.register('03a', 'Evidence', 'growth', 'amber', 'agent', 'Evidence only.',
                   profile='test-profile', owners=[('marketer', 'owner'), ('reviewer', 'countersigner')])
        for board, agent in [('people', '10'), ('growth', '03a')]:
            folder = aos.BOARDS / board
            folder.mkdir(parents=True)
            with sqlite3.connect(folder / 'kanban.db') as con:
                con.executescript('''
                    CREATE TABLE tasks (
                      id TEXT PRIMARY KEY, title TEXT, body TEXT, status TEXT,
                      priority INTEGER, assignee TEXT, tenant TEXT, result TEXT,
                      completed_at INTEGER, consecutive_failures INTEGER,
                      last_failure_error TEXT, last_heartbeat_at INTEGER, created_at INTEGER);
                    CREATE TABLE task_attachments (
                      id INTEGER PRIMARY KEY, task_id TEXT, filename TEXT,
                      stored_path TEXT, content_type TEXT, size INTEGER,
                      uploaded_by TEXT, created_at INTEGER);
                    CREATE TABLE task_runs (
                      id INTEGER PRIMARY KEY, task_id TEXT, profile TEXT, status TEXT,
                      outcome TEXT, summary TEXT, error TEXT, started_at INTEGER,
                      ended_at INTEGER, worker_pid INTEGER);
                ''')
                con.execute('INSERT INTO tasks VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)',
                            ('task', 'Example work', 'Original brief', 'blocked', 3,
                             'test-profile', 'agent-' + agent, '', None, 0, None, None, 1))
            con.close()
        self.client = TestClient(web.app, raise_server_exceptions=False)
        self.addCleanup(self.client.close)

    def add_file(self, board='people'):
        path = aos.BOARDS / board / 'draft.md'
        path.write_text('Reviewable output', encoding='utf-8')
        con = sqlite3.connect(aos.BOARDS / board / 'kanban.db')
        con.execute('INSERT INTO task_attachments VALUES (?,?,?,?,?,?,?,?)',
                    (1, 'task', 'draft.md', str(path), 'text/markdown', path.stat().st_size, 'fixture', 1))
        con.commit()
        con.close()
        return path

    def test_green_file_preview_renders_contents(self):
        self.add_file()
        response = self.client.get('/file/people/task/1?as=owner')
        self.assertEqual(response.status_code, 200)
        self.assertIn('Reviewable output', response.text)

    def test_task_page_states_progress_not_just_who_ran_it(self):
        # Blocked: the fixture's default. Must read as stopped, not silent.
        page = self.client.get('/task/people/task?as=owner')
        self.assertIn('Stopped', page.text)
        self.assertNotIn('Completed by', page.text)

        con = sqlite3.connect(aos.BOARDS / 'people' / 'kanban.db')
        con.execute("UPDATE tasks SET status='in_progress' WHERE id='task'")
        con.commit()
        con.close()
        page = self.client.get('/task/people/task?as=owner')
        self.assertIn('Working on it now', page.text)

        con = sqlite3.connect(aos.BOARDS / 'people' / 'kanban.db')
        con.execute("UPDATE tasks SET status='done', completed_at=1 WHERE id='task'")
        con.commit()
        con.close()
        page = self.client.get('/task/people/task?as=owner')
        self.assertIn('Finished', page.text)
        self.assertIn('Completed by', page.text)

    def test_signing_journey_from_preview_through_release(self):
        path = self.add_file('growth')
        page = self.client.get('/file/growth/task/1?as=reviewer')
        self.assertIn('Awaiting your decision', page.text)
        reviewed = hashlib.sha256(path.read_bytes()).hexdigest()
        self.assertIn(reviewed, page.text)

        posted = self.client.post('/sign/growth/task', data={
            'user': 'reviewer', 'decision': 'approved', 'artifact': str(path),
            'expected_hash': reviewed, 'note': 'Checked against the brief.',
            'back': '/'}, follow_redirects=False)
        self.assertEqual(posted.status_code, 303)
        # Released: consumers and owners can now download.
        self.assertEqual(self.client.get('/file/growth/task/1/raw?as=marketer').status_code, 200)
        # The recorded decision names the signer and the reviewed bytes.
        con = sqlite3.connect(aos.APPROVALS_DB)
        row = con.execute('SELECT signer, decision, artifact_hash, note FROM approvals').fetchone()
        con.close()
        self.assertEqual(row[0], 'reviewer')
        self.assertEqual(row[1], 'approved')
        self.assertIn(reviewed, row[2])
        self.assertEqual(row[3], 'Checked against the brief.')

    def test_signing_refuses_when_file_changed_between_preview_and_approve(self):
        path = self.add_file('growth')
        stale = hashlib.sha256(path.read_bytes()).hexdigest()
        path.write_text('Rewritten while the reviewer was reading', encoding='utf-8')
        response = self.client.post('/sign/growth/task', data={
            'user': 'reviewer', 'decision': 'approved', 'artifact': str(path),
            'expected_hash': stale, 'back': '/'}, follow_redirects=False)
        self.assertEqual(response.status_code, 409)
        self.assertIn('changed since preview', response.text)
        self.assertEqual(self.client.get('/file/growth/task/1/raw?as=marketer').status_code, 403)

    def set_done(self, board='growth'):
        con = sqlite3.connect(aos.BOARDS / board / 'kanban.db')
        con.execute("UPDATE tasks SET status='done', completed_at=1 WHERE id='task'")
        con.commit()
        con.close()

    def test_rejected_task_shows_rejected_not_signed(self):
        path = self.add_file('growth')
        self.set_done()
        self.client.post('/sign/growth/task', data={
            'user': 'reviewer', 'decision': 'rejected', 'artifact': str(path),
            'expected_hash': hashlib.sha256(path.read_bytes()).hexdigest(),
            'note': 'Overstates the evidence.', 'back': '/'},
            follow_redirects=False)
        listing = self.client.get('/agent/03a?as=reviewer')
        self.assertIn('rejected', listing.text)
        self.assertNotIn('>signed<', listing.text)
        task_page = self.client.get('/task/growth/task?as=reviewer')
        self.assertIn('Rejected. Not releasable.', task_page.text)
        # Still in the queue — someone has to act on it.
        self.assertIn('Example work', self.client.get('/?as=reviewer').text)

    def test_amber_reviewer_can_preview_but_owner_cannot_release(self):
        self.add_file('growth')
        response = self.client.get('/file/growth/task/1?as=reviewer')
        self.assertEqual(response.status_code, 200)
        self.assertIn('Reviewable output', response.text)
        self.assertIn('name="expected_hash"', response.text)
        self.assertEqual(self.client.get('/file/growth/task/1?as=marketer').status_code, 403)
        self.assertEqual(self.client.get('/file/growth/task/1/raw?as=reviewer').status_code, 403)
        self.assertEqual(self.client.get('/file/growth/task/1/review-raw?as=reviewer').status_code, 200)
        self.assertEqual(self.client.get('/file/growth/task/1/review-raw?as=marketer').status_code, 403)

    def test_validation_preserves_submitted_fields(self):
        with patch.object(aos, 'create_task', side_effect=ValueError('Source is required')):
            response = self.client.post('/new', data={
                'user': 'owner', 'agent_no': '10', 'title': 'PRESERVED TITLE',
                'body': 'PRESERVED BRIEF', 'priority': '2'})
        self.assertEqual(response.status_code, 422)
        self.assertIn('PRESERVED TITLE', response.text)
        self.assertIn('PRESERVED BRIEF', response.text)
        self.assertIn('value="2" selected', response.text)
        self.assertIn('Source is required', response.text)

    def test_mutations_refuse_non_development_stub_before_side_effect(self):
        with patch.object(web, 'AOS_ENV', 'production'), \
             patch.object(aos, 'create_task') as create, \
             patch.object(aos, 'unblock') as unblock, \
             patch.object(aos, 'sign') as sign:
            cases = [
                ('/new', {'user': 'owner', 'agent_no': '10', 'title': 'Test'}),
                ('/unblock/people/task', {'user': 'owner'}),
                ('/sign/growth/task', {'user': 'reviewer', 'decision': 'approved',
                  'artifact': 'unused', 'expected_hash': '0' * 64}),
            ]
            for url, data in cases:
                with self.subTest(url=url):
                    response = self.client.post(url, data=data, follow_redirects=False)
                    self.assertEqual(response.status_code, 500)
                    self.assertIn('Stubbed auth', response.text)
            create.assert_not_called()
            unblock.assert_not_called()
            sign.assert_not_called()

    def test_task_authorizes_before_reading_and_missing_task_is_404(self):
        with patch.object(aos, '_get_task', wraps=aos._get_task) as read:
            response = self.client.get('/task/growth/task?as=owner')
            self.assertEqual(response.status_code, 403)
            read.assert_not_called()
        response = self.client.get('/task/people/missing?as=owner')
        self.assertEqual(response.status_code, 404)

    def test_retry_returns_to_valid_origin_after_one_cli_call(self):
        with patch.object(aos, '_kanban', return_value='') as cli:
            response = self.client.post('/unblock/people/task',
                data={'user': 'owner', 'back': '/agent/10'}, follow_redirects=False)
        self.assertEqual(response.status_code, 303)
        self.assertEqual(response.headers['location'], '/agent/10?as=owner')
        cli.assert_called_once_with('people', 'unblock', 'task')


if __name__ == '__main__':
    unittest.main()
