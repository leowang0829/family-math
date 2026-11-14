"""Verify HTTPS proxy boundaries using an isolated database and no AI calls."""
import json
import hashlib
import sqlite3
import time
import threading
import unittest
from unittest.mock import patch
from test_server import HTTPTests, server


class CloudTests(unittest.TestCase):
    request = HTTPTests.request
    tearDown = HTTPTests.tearDown
    def setUp(self):
        HTTPTests.setUp(self)
        self.app.public_origin = 'https://math.example.ts.net'
        self.app.public_host = 'math.example.ts.net'

    def cloud(self, path, body=None, headers=None):
        return self.request(path, body, {
            'Host': self.app.public_host,
            'Origin': self.app.public_origin,
            **(headers or {}),
        })

    # Only cloud-specific tests; inherited LAN contracts are exercised separately.
    def test_cloud_pair_upload_and_read(self):
        status, headers, _ = self.cloud('/api/pair', {'code': self.app.pair_code})
        self.assertEqual(status, 200)
        self.assertIn('; Secure', headers['Set-Cookie'])
        self.cookie = headers['Set-Cookie'].split(';')[0]
        from test_server import IMAGE
        status, _, raw = self.cloud('/api/questions', {'client_id': 'cloud-photo', 'image': IMAGE})
        self.assertEqual(status, 201)
        ident = json.loads(raw)['question']['id']
        self.assertEqual(self.cloud('/api/questions/' + ident + '/photo')[0], 200)
        self.assertEqual(json.loads(self.cloud('/api/health')[2])['storage'], '云端')

    def test_cloud_blocks_setup_even_with_loopback_or_spoofed_forward_headers(self):
        for path in ['/setup', '/api/setup', '/api/setup/backup']:
            self.assertEqual(self.cloud(path)[0], 403)
            self.assertEqual(self.request(path, headers={'Tailscale-User-Login': 'someone'})[0], 403)

    def test_cloud_rejects_cross_origin_and_unknown_hosts(self):
        body = {'code': self.app.pair_code}
        self.assertEqual(self.cloud('/api/pair', body, {'Origin': 'https://evil.example'})[0], 403)
        self.assertEqual(self.cloud('/api/pair', body, {'Origin': 'http://' + self.app.public_host})[0], 403)
        self.assertEqual(self.cloud('/api/health', headers={'Host': 'evil.example'})[0], 403)
        self.assertEqual(self.cloud('/api/pair', body, {'Host': 'evil.example', 'X-Forwarded-Host': self.app.public_host})[0], 403)

    def test_cloud_rejects_bad_origin_configuration(self):
        for origin in ['http://math.example.ts.net', 'https://user:pass@host.ts.net', 'https://host.ts.net/path', 'https://host.ts.net?x=1']:
            with self.subTest(origin=origin), self.assertRaises(ValueError):
                server.App(self.temp.name, '127.0.0.1', 8921, origin)
        with self.assertRaises(ValueError):
            server.App(self.temp.name, '192.168.1.10', 8921, self.app.public_origin)

    def test_restart_resumes_in_flight_work_without_live_ai(self):
        from test_server import IMAGE
        q = self.app.save_question({'client_id': 'interrupted', 'image': IMAGE})
        with self.app.db() as db:
            db.execute("UPDATE questions SET status='processing',is_import=1,collection_version=2,solve_mode='careful' WHERE id=?", (q['id'],))
        restored = server.App(self.temp.name, '127.0.0.1', self.app.port, self.app.public_origin)
        started = threading.Event()
        try:
            with patch.object(restored, 'config', return_value={'key': 'fixture-only'}), patch.object(restored, 'start_solve', side_effect=lambda *a, **kw: started.set()) as solve:
                restored.resume_automatic_review()
                self.assertTrue(started.wait(3))
                solve.assert_called_once_with(q['id'], mode='careful', auto_collect=True)
                restored.stopping.set()
        finally:
            restored.stopping.set()
            restored.pool.shutdown(wait=True)
            restored.practice_pool.shutdown(wait=True)


class PublicAccessTests(unittest.TestCase):
    request = HTTPTests.request
    tearDown = HTTPTests.tearDown
    cloud = CloudTests.cloud

    def setUp(self):
        HTTPTests.setUp(self)
        self.app.public_host = 'math.example.ts.net'
        self.app.public_origin = 'https://' + self.app.public_host
        self.app.public_access = True
        self.password = 'fixture-only-long-password'
        self.access = {'algorithm': 'pbkdf2-sha256', 'iterations': 600000, 'salt': '10' * 16}
        self.access['hash'] = hashlib.pbkdf2_hmac('sha256', self.password.encode(), bytes.fromhex(self.access['salt']), self.access['iterations']).hex()
        self.app.access_config = self.access

    def test_public_requires_password_and_secure_session(self):
        self.assertEqual(self.cloud('/api/questions')[0], 401)
        self.assertEqual(self.cloud('/api/pair', {'code': self.app.pair_code})[0], 401)
        self.assertEqual(self.cloud('/api/pair', {'code': 'wrong'})[0], 401)
        status, headers, raw = self.cloud('/api/pair', {'code': self.password})
        self.assertEqual(status, 200)
        self.assertIn('; Secure', headers['Set-Cookie'])
        self.assertEqual(json.loads(raw)['login_mode'], 'password')
        self.assertNotIn(self.password.encode(), raw)
        self.cookie = headers['Set-Cookie'].split(';')[0]
        self.assertEqual(self.cloud('/api/questions')[0], 200)

    def test_legacy_private_session_cannot_unlock_public(self):
        token = 'legacy-fixture'
        with self.app.db() as db:
            db.execute('INSERT INTO sessions VALUES(?,?)', (hashlib.sha256(token.encode()).hexdigest(), time.time() + 1000))
        self.cookie = 'math_session=' + token
        self.assertEqual(self.cloud('/api/questions')[0], 401)

    def test_public_proxy_limits_each_client_without_locking_other_families(self):
        first = {'X-Real-IP': '192.0.2.1'}
        for _ in range(10):
            self.assertEqual(self.cloud('/api/pair', {'code': 'wrong'}, first)[0], 401)
        self.assertEqual(self.cloud('/api/pair', {'code': self.password}, first)[0], 429)
        self.assertEqual(self.cloud('/api/pair', {'code': self.password}, {'X-Real-IP': '192.0.2.2'})[0], 200)

    def test_invalid_proxy_address_cannot_bypass_limit(self):
        for _ in range(10):
            self.assertEqual(self.cloud('/api/pair', {'code': 'wrong'}, {'X-Real-IP': 'invalid'})[0], 401)
        self.assertEqual(self.cloud('/api/pair', {'code': self.password}, {'X-Real-IP': 'another-invalid'})[0], 429)

    def test_login_body_limit_and_unauthenticated_upload_guard(self):
        self.assertEqual(self.cloud('/api/pair', {'code': 'x' * 2100})[0], 413)
        self.assertEqual(self.cloud('/api/questions', {'image': 'x' * 2100})[0], 401)

    def test_public_start_fails_closed_without_password_config(self):
        with self.assertRaises(FileNotFoundError):
            server.App(self.temp.name, '127.0.0.1', 8921, self.app.public_origin, public_access=True)
        path = self.app.data / 'access-config.json'
        path.write_text(json.dumps(self.access))
        app = server.App(self.temp.name, '127.0.0.1', 8921, self.app.public_origin, public_access=True)
        try:
            self.assertTrue(app.login_valid(self.password))
            self.assertFalse(app.login_valid(app.pair_code))
            self.assertEqual(path.stat().st_mode & 0o777, 0o600)
        finally:
            app.pool.shutdown(wait=True)
            app.practice_pool.shutdown(wait=True)


if __name__ == '__main__':
    unittest.main()
