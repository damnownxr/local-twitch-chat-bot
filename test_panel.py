import copy
import json
import re
import shutil
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch

import requests
import bot
import panel


class PanelTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        for name in ['config.json', 'blocklist.json', 'panel.html']:
            shutil.copy(panel.ROOT / name, self.root / name)
        self.patches = [patch.object(panel, 'ROOT', self.root), patch.object(bot, 'ROOT', self.root)]
        for p in self.patches:
            p.start()
        self.server = panel.create_server(0)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.base = f'http://127.0.0.1:{self.server.server_address[1]}'
        html = requests.get(self.base, timeout=3).text
        self.token = re.search("const TOKEN='([^']+)'", html).group(1)
        self.headers = {'X-Panel-Token': self.token}
        self.state = requests.get(self.base + '/api/state', headers=self.headers, timeout=3).json()

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=3)
        for p in reversed(self.patches):
            p.stop()
        self.temp.cleanup()

    def post(self, path, data, headers=None):
        return requests.post(self.base + path, headers=self.headers if headers is None else headers, json=data, timeout=3)

    def test_no_token_denied(self):
        self.assertEqual(self.post('/api/config', {}, {}).status_code, 403)
        self.assertEqual(requests.get(self.base + '/api/state', timeout=3).status_code, 403)

    def test_other_origin_denied(self):
        headers = {**self.headers, 'Origin': 'https://untrusted.example'}
        self.assertEqual(self.post('/api/config', {}, headers).status_code, 403)

    def test_foreign_host_denied(self):
        self.assertEqual(requests.get(self.base, headers={'Host': 'evil.example'}, timeout=3).status_code, 403)

    def test_no_secret_file_route(self):
        for path in ['/.env', '/.tokens.json', '/../bot.py']:
            self.assertEqual(requests.get(self.base + path, timeout=3).status_code, 404)

    def test_save_config_atomic_and_reload(self):
        c = self.state['config']
        c['timer']['message'] = 'Тестовая фраза'
        c['timer']['interval_minutes'] = 15
        c['moderation']['blocked_words'] = ['тестудаления']
        r = self.post('/api/config', {'value': c, 'revision': self.state['config_revision']})
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(json.loads((self.root / 'config.json').read_text())['timer']['message'], 'Тестовая фраза')
        result = self.post('/api/test', {'message': 'тестудаления'}).json()
        self.assertTrue(result['blocked'])
        self.assertNotEqual(r.json()['revision'], self.state['config_revision'])

    def test_invalid_interval_does_not_write(self):
        before = (self.root / 'config.json').read_bytes()
        c = self.state['config']
        c['timer']['interval_minutes'] = 0
        self.assertEqual(self.post('/api/config', {'value': c, 'revision': self.state['config_revision']}).status_code, 400)
        self.assertEqual((self.root / 'config.json').read_bytes(), before)

    def test_stale_revision_does_not_write(self):
        self.assertEqual(self.post('/api/config', {'value': self.state['config'], 'revision': 'stale'}).status_code, 409)

    def test_dictionary_can_add_and_remove(self):
        d = self.state['dictionary']
        d['languages']['ru']['words'] = ['панельтест']
        r = self.post('/api/dictionary', {'value': d, 'revision': self.state['dictionary_revision']})
        self.assertEqual(r.status_code, 200, r.text)
        self.assertTrue(self.post('/api/test', {'message': 'панельтест'}).json()['blocked'])
        self.assertFalse(self.post('/api/test', {'message': 'пидор'}).json()['blocked'])

    def test_disabled_filter(self):
        c = self.state['config']
        c['moderation']['enabled'] = False
        self.post('/api/config', {'value': c, 'revision': self.state['config_revision']})
        result = self.post('/api/test', {'message': 'N1GA'}).json()
        self.assertTrue(result['matched'])
        self.assertFalse(result['blocked'])

    def test_message_validation(self):
        self.assertEqual(self.post('/api/test', {'message': ''}).status_code, 400)
        self.assertEqual(self.post('/api/test', {'message': 'a' * 501}).status_code, 400)

    def test_placeholder_still_rejected_by_bot(self):
        c = copy.deepcopy(self.state['config'])
        c['channel'] = 'your_channel'
        panel.validate_settings(c)
        with self.assertRaises(ValueError):
            bot.validate_config(c)

    def test_validation_limits(self):
        with self.assertRaises(ValueError):
            panel.terms_ok(['a' * 101])
        with self.assertRaises(ValueError):
            panel.validate_dictionary({'languages': {'ru': {'words': 'not a list'}}})


if __name__ == '__main__':
    unittest.main()
