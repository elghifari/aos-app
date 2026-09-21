"""Approval-state repair: binding signatures to exact reviewed bytes.

Uses stdlib unittest — pytest is not installed in this environment.
Every fixture is a temporary SQLite DB and temp filesystem; no live board,
registry, or approvals data is read or written.
"""
import hashlib
import sqlite3
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
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
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
