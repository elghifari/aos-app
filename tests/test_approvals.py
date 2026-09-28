"""Approval-state repair: binding signatures to exact reviewed bytes.

Uses stdlib unittest — pytest is not installed in this environment.
Every fixture is a temporary SQLite DB and temp filesystem; no live board,
registry, or approvals data is read or written.
"""
import hashlib
import sqlite3
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import aos
import registry as R


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class ApprovalStateTests(unittest.TestCase):
    def setUp(self):
        self.addCleanup(lambda: aos.GATED_STAGES.pop('91b', None))
        self.addCleanup(lambda: aos.GATED_STAGES.pop('91c', None))
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
        ]:
            p = patch.object(target, name, value)
            p.start()
            self.addCleanup(p.stop)
        R.init_registry()
        aos.init_approvals()
        # Two boards. 'signer' countersigns agent 91 (board one) and 93
        # (board two); 'other' countersigns 92 only, so cross-agent and
        # cross-board authority can be tested.
        for agent, board, countersigner in [('91', 'one', 'signer'),
                                            ('92', 'one', 'other'),
                                            ('93', 'two', 'signer')]:
            R.register(agent, 'Test agent', board, 'amber', 'seat',
                       'Test guardrail',
                       owners=[('owner', 'owner'), (countersigner, 'countersigner'),
                               ('reader', 'consumer')])
        for board, agent in [('one', '91'), ('two', '93')]:
            root = aos.BOARDS / board
            root.mkdir(parents=True)
            con = sqlite3.connect(root / 'kanban.db')
            con.executescript('''
                CREATE TABLE tasks (id TEXT PRIMARY KEY, title TEXT, body TEXT,
                  status TEXT, priority INTEGER, assignee TEXT, tenant TEXT,
                  result TEXT, completed_at INTEGER);
                CREATE TABLE task_attachments (id INTEGER PRIMARY KEY, task_id TEXT,
                  filename TEXT, stored_path TEXT, content_type TEXT, size INTEGER,
                  uploaded_by TEXT, created_at INTEGER);
            ''')
            for task in ['t', 'unrelated']:
                con.execute("INSERT INTO tasks VALUES (?,?,?,'done',3,NULL,?,NULL,1)",
                            (task, task, 'Original brief', R.tenant_for(agent)))
            for n, task in [(1, 't'), (2, 't'), (3, 'unrelated')]:
                path = root / f'{n}.txt'
                path.write_text(f'Artifact {n}', encoding='utf-8')
                con.execute('INSERT INTO task_attachments VALUES (?,?,?,?,?,?,?,1)',
                            (n, task, path.name, str(path), 'text/plain',
                             path.stat().st_size, 'owner'))
            con.commit()
            con.close()

    def artifact(self, number=1, board='one'):
        return aos.BOARDS / board / f'{number}.txt'

    def approve(self, number=1, decision='approved', board='one', task='t'):
        path = self.artifact(number, board)
        return aos.sign(board, task, 'signer', 'countersigner', decision,
                        str(path), expected_hash=digest(path))

    def stage_task(self, task_id, agent, status='done', board='one'):
        con = sqlite3.connect(aos.BOARDS / board / 'kanban.db')
        con.execute("INSERT INTO tasks VALUES (?,?,?,?,3,NULL,?,NULL,1)",
                    (task_id, task_id, 'brief', status, R.tenant_for(agent)))
        con.commit()
        con.close()

    def test_standing_rules_are_prepended_so_briefs_can_be_short(self):
        # A two-line brief from a busy staff member must still produce a
        # run bound by the agent's rules. Safety lives in the role, not in
        # the requester's typing.
        R.register('95', 'Evidence Table', 'one', 'amber', 'agent',
                   'Evidence table only. KURI ceiling at this stage.',
                   profile='pod-test',
                   owners=[('owner', 'owner'), ('reviewer', aos.AMBER_SIGNER_ROLE)])
        aos.STANDING_RULES['95'] = ['Only cite a source you opened.',
                                    'List failed lookups under COULD NOT VERIFY.']
        self.addCleanup(lambda: aos.STANDING_RULES.pop('95', None))

        calls = []
        with patch.object(aos, '_kanban',
                          side_effect=lambda b, *a: calls.append(a) or '{"id":"t1"}'):
            aos.create_task('owner', 'one', '95', 'Cari bukti TMS',
                            'Cari bukti ilmiah TMS depresi remaja. 8-12 sumber, DOI wajib.')

        body = next(x for c in calls for x in c if 'Cari bukti ilmiah' in str(x))
        self.assertIn('Only cite a source you opened.', body)
        self.assertIn('COULD NOT VERIFY', body)
        self.assertIn('Evidence table only', body)      # registry guardrail
        self.assertIn('Cari bukti ilmiah', body)        # the brief itself
        self.assertLess(body.index('Only cite'), body.index('Cari bukti ilmiah'),
                        'rules must precede the brief')

    def test_an_agent_without_role_rules_still_gets_delivery_requirement(self):
        R.register('96', 'Plain agent', 'one', 'green', 'agent', 'Runs.',
                   profile='p', owners=[('owner', 'owner')])
        calls = []
        with patch.object(aos, '_kanban',
                          side_effect=lambda b, *a: calls.append(a) or '{"id":"t1"}'):
            aos.create_task('owner', 'one', '96', 'JD batch', 'Write three JDs.')
        body = next(x for c in calls for x in c if 'Write three JDs' in str(x))
        self.assertNotIn('COULD NOT VERIFY', body)
        self.assertIn('include every output file in kanban_complete artifacts', body)
        self.assertTrue(body.endswith('Write three JDs.'))

    def test_agentic_work_requires_a_preserved_deliverable(self):
        R.register('97', 'Evidence worker', 'one', 'green', 'agent', 'Runs.',
                   profile='p', owners=[('owner', 'owner')])
        calls = []
        with patch.object(aos, '_kanban',
                          side_effect=lambda b, *a: calls.append(a) or '{"id":"t1"}'):
            aos.create_task('owner', 'one', '97', 'Evidence table', 'Write the table.')

        create = next(c for c in calls if c[0] == 'create')
        body = create[create.index('--body') + 1]
        self.assertNotIn('--completion-contract', create)
        self.assertIn('include every output file in kanban_complete artifacts', body)

    def test_creating_work_for_an_agent_dispatches_it_immediately(self):
        R.register('94', 'Worker agent', 'one', 'green', 'agent', 'Runs.',
                   profile='p', owners=[('owner', 'owner')])
        with patch.object(aos, '_kanban', return_value='{"id":"new"}') as cli:
            aos.create_task('owner', 'one', '94', 'Draft a JD', 'brief')
        calls = [c.args[1] for c in cli.call_args_list]
        create = next(c.args for c in cli.call_args_list if c.args[1] == 'create')
        self.assertEqual(create[create.index('--assignee') + 1], 'p')
        self.assertNotIn('assign', calls)
        self.assertGreater(calls.index('dispatch'), calls.index('create'))

    def test_seat_work_is_not_dispatched(self):
        R.register('95', 'FTE model', 'one', 'green', 'seat', 'Human work.',
                   owners=[('owner', 'owner')])
        with patch.object(aos, '_kanban', return_value='{"id":"new"}') as cli:
            aos.create_task('owner', 'one', '95', 'Model FTE', 'brief')
        calls = [c.args[1] for c in cli.call_args_list]
        self.assertNotIn('dispatch', calls)
        self.assertNotIn('assign', calls)

    def test_dispatch_failure_does_not_lose_the_task(self):
        R.register('96', 'Worker agent', 'one', 'green', 'agent', 'Runs.',
                   profile='p', owners=[('owner', 'owner')])
        def flaky(board, *args):
            if args[0] == 'dispatch':
                raise subprocess.CalledProcessError(1, 'hermes')
            return '{"id":"new"}'
        with patch.object(aos, '_kanban', side_effect=flaky):
            # The task exists; only the immediate start failed. The gateway
            # tick will pick it up, so this must not raise.
            self.assertEqual(
                aos.create_task('owner', 'one', '96', 'Draft', 'brief'), 'new')

    def test_gated_stage_refuses_until_the_prior_stage_is_approved(self):
        # 03b-equivalent: a stage behind a human gate.
        R.register('91b', 'Drafter', 'one', 'amber', 'agent', 'From the claim set only.',
                   profile='p', owners=[('owner', 'owner'), ('signer', 'countersigner')])
        aos.GATED_STAGES['91b'] = '91'

        # Nothing approved upstream -> refuse, naming what is missing.
        with self.assertRaisesRegex(aos.GateNotPassed, 'approved'):
            aos.create_task('owner', 'one', '91b', 'Draft the article', 'brief')

        # An upstream task that is merely DONE is not enough.
        with self.assertRaises(aos.GateNotPassed):
            aos.create_task('owner', 'one', '91b', 'Draft the article', 'brief')

        # Approve the upstream artifact, and the stage opens.
        self.approve(1)
        with patch.object(aos, '_kanban', return_value='{"id": "child"}') as cli:
            task_id = aos.create_task('owner', 'one', '91b', 'Draft', 'brief')
        self.assertEqual(task_id, 'child')
        # The approved file is carried forward, not retyped.
        call = next(c.args for c in cli.call_args_list if c.args[1] == 'create')
        body = call[call.index('--body') + 1]
        self.assertIn('APPROVED CLAIM SET', body)
        self.assertIn('1.txt', body)
        self.assertIn('brief', body)
        self.assertNotIn('--assignee', call)
        calls = [c.args[1] for c in cli.call_args_list]
        self.assertLess(calls.index('link'), calls.index('assign'))

    def test_ungated_agents_are_unaffected(self):
        with patch.object(aos, '_kanban', return_value='{"id": "x"}'):
            self.assertEqual(
                aos.create_task('owner', 'one', '91', 'Evidence table', 'brief'), 'x')

    def test_rejected_upstream_does_not_open_the_gate(self):
        R.register('91c', 'Drafter', 'one', 'amber', 'agent', 'From the claim set only.',
                   profile='p', owners=[('owner', 'owner'), ('signer', 'countersigner')])
        aos.GATED_STAGES['91c'] = '91'
        self.approve(1, 'rejected')
        with self.assertRaises(aos.GateNotPassed):
            aos.create_task('owner', 'one', '91c', 'Draft', 'brief')

    def test_rejected_work_reads_as_rejected_and_stays_in_the_queue(self):
        self.approve(1, 'rejected')
        self.approve(2)
        task = next(t for t in aos.agent_tasks('signer', '91') if t['id'] == 't')
        self.assertEqual(task['review_state'], 'rejected')
        self.assertFalse(task['signed'])
        self.assertIn('t', [q['id'] for q in aos.unsigned_amber('signer')])
        with self.assertRaises(aos.NotSigned):
            aos.attachment('reader', 'one', 't', '1')
        # The signer can still open it to re-review after changes.
        again = aos.attachment('signer', 'one', 't', '1', review=True)
        self.assertEqual(again['signature']['state'], 'rejected')

    def test_task_leaves_the_queue_only_when_every_file_is_approved(self):
        self.approve(1)
        queue = [q['id'] for q in aos.unsigned_amber('signer') if q['board'] == 'one']
        self.assertIn('t', queue)
        self.approve(2)
        task = next(t for t in aos.agent_tasks('signer', '91') if t['id'] == 't')
        self.assertEqual(task['review_state'], 'approved')
        self.assertTrue(task['signed'])
        queue = [q['id'] for q in aos.unsigned_amber('signer') if q['board'] == 'one']
        self.assertNotIn('t', queue)

    def test_latest_decision_wins_when_timestamps_collide(self):
        with patch.object(aos.time, 'time', return_value=100):
            self.approve(1)
            self.approve(1, 'rejected')
            self.approve(1)
        self.assertEqual(
            aos.attachment('signer', 'one', 't', '1', review=True)['signature']['state'],
            'approved')

    def test_legacy_bare_hash_releases_only_its_own_exact_bytes(self):
        path = self.artifact(1)
        con = sqlite3.connect(aos.APPROVALS_DB)
        con.execute("""INSERT INTO approvals (board, task_id, agent_no, signer,
            signer_role, decision, note, artifact_hash, signed_at)
            VALUES (?,?,?,?,?,?,?,?,?)""",
                    ('one', 't', '91', 'signer', 'countersigner', 'approved',
                     'legacy row', digest(path), 50))
        con.commit()
        con.close()
        # Honoured for the file it was recorded against...
        self.assertEqual(aos.attachment('reader', 'one', 't', '1')['id'], 1)
        # ...but it must not release a sibling, even with identical bytes.
        self.artifact(2).write_bytes(path.read_bytes())
        with self.assertRaises(aos.NotSigned):
            aos.attachment('reader', 'one', 't', '2')

    def test_release_is_bound_to_one_attachment_and_its_current_bytes(self):
        self.approve(1)
        self.assertEqual(aos.attachment('reader', 'one', 't', '1')['path'].name,
                         '1.txt')
        # A sibling attachment, another task, and the same-numbered file on
        # a different board must all stay closed.
        for board, task, att in [('one', 't', '2'), ('one', 'unrelated', '3'),
                                 ('two', 't', '1')]:
            with self.subTest(board=board, task=task, att=att), \
                 self.assertRaises(aos.NotSigned):
                aos.attachment('reader', board, task, att)
        # Task-level release still false: attachment 2 is unapproved.
        self.assertFalse(aos.signature_state('one', 't')['approved'])
        # Tamper after approval revokes access rather than serving it.
        self.artifact(1).write_text('Tampered after sign-off', encoding='utf-8')
        with self.assertRaises(aos.NotSigned):
            aos.attachment('reader', 'one', 't', '1')

    def test_identical_bytes_still_need_their_own_decision(self):
        self.artifact(2).write_bytes(self.artifact(1).read_bytes())
        self.approve(1)
        with self.assertRaises(aos.NotSigned):
            aos.attachment('reader', 'one', 't', '2')
        self.approve(2)
        self.assertTrue(aos.signature_state('one', 't')['approved'])

    def test_qualified_signer_reviews_before_signing_but_cannot_release(self):
        att = aos.attachment('signer', 'one', 't', '1', review=True)
        self.assertEqual(att['artifact_hash'], digest(att['path']))
        self.assertTrue(att['can_sign'])
        self.assertEqual(att['signature']['state'], 'pending')
        # Review access is not release: the ordinary path stays shut.
        with self.assertRaises(aos.NotSigned):
            aos.attachment('signer', 'one', 't', '1')
        # And review is limited to the agent's own countersigner.
        for user in ['owner', 'reader', 'other', 'stranger']:
            with self.subTest(user=user), self.assertRaises(PermissionError):
                aos.attachment(user, 'one', 't', '1', review=True)

    def test_sign_refuses_paths_that_are_not_this_tasks_attachment(self):
        outside = self.root / 'outside.txt'
        outside.write_text('Outside the board entirely', encoding='utf-8')
        with self.assertRaises(PermissionError):
            aos.sign('one', 't', 'signer', 'countersigner', 'approved',
                     str(outside), expected_hash=digest(outside))
        # On the board, but belongs to a different task.
        sibling = self.artifact(3)
        with self.assertRaisesRegex(ValueError, 'not an attachment of this task'):
            aos.sign('one', 't', 'signer', 'countersigner', 'approved',
                     str(sibling), expected_hash=digest(sibling))
        path = self.artifact()
        with self.assertRaisesRegex(ValueError, 'expected_hash'):
            aos.sign('one', 't', 'signer', 'countersigner', 'approved',
                     str(path), expected_hash='')
        with self.assertRaisesRegex(ValueError, 'approved'):
            aos.sign('one', 't', 'signer', 'countersigner', 'maybe',
                     str(path), expected_hash=digest(path))
        con = sqlite3.connect(aos.APPROVALS_DB)
        recorded = con.execute('SELECT COUNT(*) FROM approvals').fetchone()[0]
        con.close()
        self.assertEqual(recorded, 0)

    def test_sign_refuses_signer_without_authority_for_that_agent(self):
        path = self.artifact()
        for impostor in ['owner', 'reader', 'other', 'stranger']:
            with self.subTest(signer=impostor), self.assertRaises(PermissionError):
                aos.sign('one', 't', impostor, 'countersigner', 'approved',
                         str(path), expected_hash=digest(path))

    def test_sign_refuses_bytes_that_changed_since_preview(self):
        path = self.artifact()
        reviewed = digest(path)
        path.write_text('Swapped after the reviewer read it', encoding='utf-8')
        with self.assertRaisesRegex(ValueError, 'changed'):
            aos.sign('one', 't', 'signer', 'countersigner', 'approved',
                     str(path), expected_hash=reviewed)
        con = sqlite3.connect(aos.APPROVALS_DB)
        recorded = con.execute('SELECT COUNT(*) FROM approvals').fetchone()[0]
        con.close()
        self.assertEqual(recorded, 0)


if __name__ == '__main__':
    unittest.main()
