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
        # Board connections are pooled; a handle to a previous test's
        # temp dir must not survive into this one.
        aos._close_pool()
        self.addCleanup(aos._close_pool)
        self.root = Path(self.tmp.name)
        for target, name, value in [
            (R, 'REGISTRY_DB', self.root / 'registry.db'),
            (aos, 'APPROVALS_DB', self.root / 'approvals.db'),
            (aos, 'BOARDS', self.root / 'boards'),
            (aos, 'PROFILES', self.root / 'profiles'),
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

    def test_home_shows_the_users_actual_work_not_just_empty_queues(self):
        self.add_file()
        con = sqlite3.connect(aos.BOARDS / 'people' / 'kanban.db')
        con.execute("UPDATE tasks SET status='done', completed_at=1 WHERE id='task'")
        con.execute("""INSERT INTO tasks (id,title,body,status,priority,assignee,tenant,created_at)
                       VALUES ('running','Drafting JDs now','b','running',3,'p','agent-10',1)""")
        con.execute("""INSERT INTO tasks (id,title,body,status,priority,assignee,tenant,created_at)
                       VALUES ('old','Archived clutter','b','archived',3,'p','agent-10',1)""")
        con.commit()
        con.close()
        page = self.client.get('/?as=owner')
        self.assertIn('Drafting JDs now', page.text)   # in progress, visible
        self.assertIn('Example work', page.text)       # finished, visible
        self.assertNotIn('Archived clutter', page.text)  # archived, hidden

    def test_archived_tasks_are_hidden_from_the_agent_view(self):
        con = sqlite3.connect(aos.BOARDS / 'people' / 'kanban.db')
        con.execute("""INSERT INTO tasks (id,title,body,status,priority,assignee,tenant,created_at)
                       VALUES ('old','CONCURRENCY-TEST-A','b','archived',3,'p','agent-10',1)""")
        con.commit()
        con.close()
        page = self.client.get('/agent/10?as=owner')
        self.assertNotIn('CONCURRENCY-TEST-A', page.text)

    def test_every_real_kanban_status_has_plain_language(self):
        # The authoritative set, from `hermes kanban list --status`.
        # A status missing here renders as "Unknown" to the user, which is
        # what happened when this map guessed 'in_progress' instead of
        # reading the CLI's actual vocabulary.
        for status in ['archived', 'blocked', 'done', 'ready', 'review',
                       'running', 'scheduled', 'todo', 'triage']:
            with self.subTest(status=status):
                p = aos.progress({'status': status})
                self.assertNotEqual(p['label'], 'Unknown')
                self.assertNotIn('Board status', p['detail'])
        self.assertTrue(aos.progress({'status': 'running'})['running'])
        self.assertTrue(aos.progress({'status': 'done'})['finished'])
        self.assertTrue(aos.progress({'status': 'blocked'})['stopped'])

    def test_task_page_shows_only_the_request_not_worker_instructions(self):
        con = sqlite3.connect(aos.BOARDS / 'growth' / 'kanban.db')
        con.execute("UPDATE tasks SET body=? WHERE id='task'", (
            '## DELIVERY REQUIREMENT\nKeep this internal.\n\n## THE REQUEST\n\nFind adolescent TMS evidence.',))
        con.commit()
        con.close()

        page = self.client.get('/task/growth/task?as=marketer')

        self.assertIn('Find adolescent TMS evidence.', page.text)
        self.assertNotIn('Keep this internal.', page.text)

    def test_completed_task_without_a_file_shows_missing_deliverable(self):
        con = sqlite3.connect(aos.BOARDS / 'growth' / 'kanban.db')
        con.execute("UPDATE tasks SET status='done', completed_at=1 WHERE id='task'")
        con.commit()
        con.close()

        page = self.client.get('/task/growth/task?as=marketer')

        self.assertIn('Missing deliverable', page.text)
        self.assertIn('cannot be reviewed or released', page.text)

    def test_legacy_back_link_is_canonicalized_and_kept_in_the_session(self):
        response = self.client.get(
            '/task/growth/task?as=marketer&back=/agent/03a', follow_redirects=False)

        self.assertEqual(response.status_code, 303)
        self.assertEqual(response.headers['location'], '/task/growth/task?as=marketer')

        page = self.client.get(response.headers['location'])
        self.assertIn('href="/agent/03a?as=marketer"', page.text)
        self.assertNotIn('back=', page.text)

    def test_sign_returns_to_the_task_from_a_session_return_path(self):
        path = self.add_file('growth')
        self.client.get('/file/growth/task/1?as=reviewer', headers={
            'referer': 'http://testserver/task/growth/task?as=reviewer'})

        response = self.client.post('/sign/growth/task', data={
            'user': 'reviewer', 'decision': 'approved', 'note': 'Checked source and scope.',
            'artifact': str(path),
            'expected_hash': hashlib.sha256(path.read_bytes()).hexdigest(),
        }, follow_redirects=False)

        self.assertEqual(response.status_code, 303)
        self.assertEqual(response.headers['location'], '/task/growth/task?as=reviewer')

    def test_unreleased_file_returns_to_the_task_with_a_popup(self):
        self.add_file('growth')
        page = self.client.get(
            '/file/growth/task/1?as=marketer&back=/task/growth/task',
            follow_redirects=True)
        self.assertEqual(page.status_code, 200)
        self.assertIn('<dialog open', page.text)
        self.assertIn('Not released yet', page.text)
        # The popup names why access is unavailable without opening a raw error page.
        self.assertIn('reviewer', page.text)

    def test_empty_artifacts_are_not_offered_for_signature(self):
        # Workers sometimes attach a stub ('null', 0 bytes) beside the real
        # deliverable. Signing that attests to nothing, and requiring it
        # blocks release of the genuine file.
        junk = aos.BOARDS / 'growth' / 'junk.md'
        junk.write_text('null', encoding='utf-8')
        con = sqlite3.connect(aos.BOARDS / 'growth' / 'kanban.db')
        con.execute('INSERT INTO task_attachments VALUES (?,?,?,?,?,?,?,?)',
                    (2, 'task', 'junk.md', str(junk), 'text/markdown',
                     junk.stat().st_size, 'worker', 1))
        con.commit()
        con.close()
        real = self.add_file('growth')

        files = aos.deliverables('reviewer', 'growth', 'task')
        self.assertTrue(all(f.get('substantive') for f in files if f['id'] == 1))
        self.assertFalse(next(f for f in files if f['id'] == 2)['substantive'])

        # Approving the real file releases the task; the stub does not block it.
        aos.sign('growth', 'task', 'reviewer', 'countersigner', 'approved',
                 str(real), expected_hash=hashlib.sha256(real.read_bytes()).hexdigest())
        self.assertTrue(aos.signature_state('growth', 'task')['approved'])

    def make_run(self, started, ended, board='growth', task='task'):
        con = sqlite3.connect(aos.BOARDS / board / 'kanban.db')
        con.execute("""INSERT INTO task_runs (task_id,profile,status,outcome,summary,
                       started_at,ended_at) VALUES (?,?,?,?,?,?,?)""",
                    (task, 'pod-test', 'done', 'completed',
                     'Verified 17 sources against PubMed.', started, ended))
        con.commit()
        con.close()

    def write_log(self, lines):
        d = aos.PROFILES / 'pod-test' / 'logs'
        d.mkdir(parents=True, exist_ok=True)
        (d / 'errors.log').write_text('\n'.join(lines), encoding='utf-8')

    def test_tool_failures_during_a_run_are_detected_from_the_log(self):
        import time as _t
        start = int(_t.time()) - 300
        end = int(_t.time()) - 60
        stamp = _t.strftime('%Y-%m-%d %H:%M:%S', _t.localtime(start + 30))
        self.make_run(start, end)
        self.write_log([
            f"{stamp},100 WARNING agent.tool_executor: Tool web_search returned error (1.1s): 403",
            f"{stamp},200 WARNING agent.tool_executor: Tool web_search returned error (1.0s): 403",
            f"{stamp},300 WARNING agent.tool_executor: Tool web_extract returned error (0.9s): 403",
        ])
        health = aos.run_integrity('growth', 'task')
        self.assertTrue(health['checked'])
        self.assertTrue(health['degraded'])
        self.assertEqual(health['failures']['web_search'], 2)
        self.assertEqual(health['failures']['web_extract'], 1)

    def test_a_clean_run_is_not_flagged(self):
        import time as _t
        self.make_run(int(_t.time()) - 300, int(_t.time()) - 60)
        self.write_log(['2020-01-01 00:00:00,000 WARNING something unrelated'])
        health = aos.run_integrity('growth', 'task')
        self.assertTrue(health['checked'])
        self.assertFalse(health['degraded'])

    def test_missing_log_is_unverified_not_clean(self):
        import time as _t
        self.make_run(int(_t.time()) - 300, int(_t.time()) - 60)
        health = aos.run_integrity('growth', 'task')
        self.assertFalse(health['checked'])
        self.assertFalse(health['degraded'])
        self.assertIn('could not', health['reason'].lower())

    def test_degraded_output_is_not_released_until_a_human_signs(self):
        import time as _t
        start, end = int(_t.time()) - 300, int(_t.time()) - 60
        stamp = _t.strftime('%Y-%m-%d %H:%M:%S', _t.localtime(start + 30))
        self.make_run(start, end)
        self.write_log([f"{stamp},100 WARNING agent.tool_executor: "
                        f"Tool web_search returned error (1.1s): 403"])
        path = self.add_file('growth')
        # Even the owner cannot collect it: the run could not reach its
        # sources, so a person must look before anyone uses it.
        with self.assertRaises(aos.NotSigned):
            aos.attachment('marketer', 'growth', 'task', '1')
        state = aos.signature_state('growth', 'task')
        self.assertFalse(state['approved'])
        self.assertIn('unreachable', state['reason'].lower())

    def test_source_warning_clears_after_qualified_human_approves(self):
        import time as _t
        start, end = int(_t.time()) - 300, int(_t.time()) - 60
        stamp = _t.strftime('%Y-%m-%d %H:%M:%S', _t.localtime(start + 30))
        self.make_run(start, end)
        self.write_log([f"{stamp},100 WARNING agent.tool_executor: "
                        f"Tool web_search returned error (1.1s): 403"])
        path = self.add_file('growth')

        before = self.client.get('/task/growth/task?as=marketer')
        self.assertIn('could not reach its sources', before.text)

        aos.sign('growth', 'task', 'reviewer', 'countersigner', 'approved',
                 str(path), expected_hash=hashlib.sha256(path.read_bytes()).hexdigest())
        after = self.client.get('/task/growth/task?as=marketer')
        self.assertNotIn('could not reach its sources', after.text)
        self.assertIn('Approved', after.text)

    def test_dismiss_is_fast_and_does_not_shell_out(self):
        # Archiving via the Hermes CLI costs ~2s of interpreter startup for
        # a one-field status change. A button that takes 3 seconds gets
        # pressed twice.
        self.add_file()
        con = sqlite3.connect(aos.BOARDS / 'people' / 'kanban.db')
        con.execute("UPDATE tasks SET status='done', completed_at=1 WHERE id='task'")
        con.commit()
        con.close()

        with patch.object(aos, '_kanban') as cli:
            aos.dismiss('owner', 'people', 'task')
        cli.assert_not_called()

        con = sqlite3.connect(aos.BOARDS / 'people' / 'kanban.db')
        status = con.execute(
            "SELECT status FROM tasks WHERE id='task'").fetchone()[0]
        con.close()
        self.assertEqual(status, 'archived')

    def test_dismissed_work_leaves_the_list_but_keeps_its_record(self):
        self.add_file()
        con = sqlite3.connect(aos.BOARDS / 'people' / 'kanban.db')
        con.execute("UPDATE tasks SET status='done', completed_at=1 WHERE id='task'")
        con.commit()
        con.close()
        aos.dismiss('owner', 'people', 'task')
        # Gone from the owner's list...
        work = aos.my_work('owner')
        self.assertNotIn('task', [t['id'] for t in work['ready']])
        # ...but the task and its signature history still resolve.
        self.assertEqual(aos._get_task('people', 'task')['status'], 'archived')

    def test_finished_work_can_be_dismissed_by_its_owner(self):
        self.add_file()
        con = sqlite3.connect(aos.BOARDS / 'people' / 'kanban.db')
        con.execute("UPDATE tasks SET status='done', completed_at=1 WHERE id='task'")
        con.commit()
        con.close()
        self.assertIn('Example work', self.client.get('/?as=owner').text)

        r = self.client.post('/dismiss/people/task',
                             data={'user': 'owner', 'back': '/'},
                             follow_redirects=False)
        self.assertEqual(r.status_code, 303)
        self.assertEqual(aos._get_task('people', 'task')['status'], 'archived')

    def test_unfinished_work_cannot_be_dismissed(self):
        # The fixture task is 'blocked'. Dismissing live work would hide a
        # problem rather than resolve it.
        with patch.object(aos, '_kanban') as cli:
            r = self.client.post('/dismiss/people/task',
                                 data={'user': 'owner', 'back': '/'},
                                 follow_redirects=True)
        self.assertEqual(r.status_code, 200)
        self.assertIn('<dialog open', r.text)
        self.assertIn('Only finished work can be dismissed', r.text)
        cli.assert_not_called()

    def test_dismissing_requires_ownership(self):
        con = sqlite3.connect(aos.BOARDS / 'growth' / 'kanban.db')
        con.execute("UPDATE tasks SET status='done', completed_at=1 WHERE id='task'")
        con.commit()
        con.close()
        with patch.object(aos, '_kanban') as cli:
            r = self.client.post('/dismiss/growth/task',
                                 data={'user': 'reviewer'}, follow_redirects=False)
        self.assertEqual(r.status_code, 403)
        cli.assert_not_called()

    def test_unsigned_amber_cannot_be_dismissed_out_of_the_queue(self):
        self.add_file('growth')
        con = sqlite3.connect(aos.BOARDS / 'growth' / 'kanban.db')
        con.execute("UPDATE tasks SET status='done', completed_at=1 WHERE id='task'")
        con.commit()
        con.close()
        with patch.object(aos, '_kanban') as cli:
            r = self.client.post('/dismiss/growth/task',
                                 data={'user': 'marketer', 'back': '/'},
                                 follow_redirects=True)
        self.assertEqual(r.status_code, 200)
        self.assertIn('<dialog open', r.text)
        self.assertIn('still waiting on review', r.text)
        cli.assert_not_called()

    def test_home_caps_the_finished_list_and_says_so(self):
        con = sqlite3.connect(aos.BOARDS / 'people' / 'kanban.db')
        for i in range(12):
            con.execute("""INSERT INTO tasks (id,title,body,status,priority,
                           assignee,tenant,created_at,completed_at)
                           VALUES (?,?,'b','done',3,'p','agent-10',1,?)""",
                        (f'done{i}', f'Finished item {i}', i))
        con.commit()
        con.close()
        page = self.client.get('/?as=owner').text
        self.assertIn('Finished item 11', page)   # newest shown
        self.assertNotIn('Finished item 0', page)  # oldest cut
        self.assertIn('8 most recent of 12', page)

    def test_cached_connection_still_sees_external_writes(self):
        # Boards are written by the Hermes dispatcher, a separate process.
        # A pooled read connection that served a stale snapshot would show
        # an owner outdated status — worse than being slow.
        first = aos._get_task('people', 'task')
        self.assertEqual(first['status'], 'blocked')
        con = sqlite3.connect(aos.BOARDS / 'people' / 'kanban.db')
        con.execute("UPDATE tasks SET status='done' WHERE id='task'")
        con.commit()
        con.close()
        self.assertEqual(aos._get_task('people', 'task')['status'], 'done')

    def test_task_page_states_progress_not_just_who_ran_it(self):
        # Blocked: the fixture's default. Must read as stopped, not silent.
        page = self.client.get('/task/people/task?as=owner')
        self.assertIn('Stopped', page.text)
        self.assertNotIn('Completed by', page.text)

        con = sqlite3.connect(aos.BOARDS / 'people' / 'kanban.db')
        con.execute("UPDATE tasks SET status='running' WHERE id='task'")
        con.commit()
        con.close()
        page = self.client.get('/task/people/task?as=owner')
        self.assertIn('Working on it now', page.text)

        con = sqlite3.connect(aos.BOARDS / 'people' / 'kanban.db')
        con.execute("UPDATE tasks SET status='done', completed_at=1 WHERE id='task'")
        con.commit()
        con.close()
        page = self.client.get('/task/people/task?as=owner')
        self.assertIn('Missing deliverable', page.text)
        self.assertNotIn('Completed by', page.text)

    def test_approved_amber_task_shows_approved_as_its_primary_status(self):
        path = self.add_file('growth')
        self.set_done()
        aos.sign('growth', 'task', 'reviewer', 'countersigner', 'approved',
                 str(path), expected_hash=hashlib.sha256(path.read_bytes()).hexdigest())

        page = self.client.get('/task/growth/task?as=marketer')
        status = page.text.split('<dt>Status</dt>', 1)[1].split('</dd>', 1)[0]
        self.assertIn('Approved', status)
        self.assertNotIn('Finished', status)

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
        owner = self.client.get('/file/growth/task/1?as=marketer')
        self.assertEqual(owner.status_code, 200)
        self.assertIn('<dialog open', owner.text)
        self.assertIn('Not released yet', owner.text)
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
