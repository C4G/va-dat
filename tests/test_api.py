"""Network-free API regression checks; no provider key or call is permitted."""
import json
import os
import threading
import unittest
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer
from unittest.mock import patch

from entry_points.api_server import AuditHandler, split_pages


class ApiTests(unittest.TestCase):
    """Exercise actual HTTP framing with a mocked pipeline."""

    @classmethod
    def setUpClass(cls):
        """Start an ephemeral loopback server."""
        cls.server = ThreadingHTTPServer(('127.0.0.1', 0), AuditHandler)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.url = f'http://127.0.0.1:{cls.server.server_port}'

    @classmethod
    def tearDownClass(cls):
        """Release the server and its listener."""
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join()

    def test_health_and_no_static_files(self):
        """The API exposes health but not the former website or secrets."""
        with urllib.request.urlopen(self.url + '/health') as response:
            self.assertEqual(json.load(response), {'status': 'ok'})
        for path in ['/', '/index.html', '/styles.css', '/.env']:
            with self.assertRaises(urllib.error.HTTPError) as error:
                urllib.request.urlopen(self.url + path)
            self.assertEqual(error.exception.code, 404)

    def test_ndjson_and_unicode(self):
        """Headers and final NDJSON result survive non-ASCII input."""
        with patch.dict(os.environ, {}, clear=True), patch('entry_points.api_server.run_audit', return_value={'success': True}) as audit:
            request = urllib.request.Request(self.url + '/api/audit', data=json.dumps({'html_content': '<p>café</p>'}).encode(), headers={'Content-Type': 'application/json'})
            with urllib.request.urlopen(request) as response:
                self.assertIn('ndjson', response.headers['Content-Type'])
                events = [json.loads(line) for line in response]
            self.assertEqual([event['type'] for event in events], ['progress', 'result'])
            self.assertEqual(audit.call_args.args[:2], ('<p>café</p>', ''))

    def test_page_splitting(self):
        """Existing nested page markers retain their URL mapping."""
        self.assertEqual(split_pages('<!-- PAGE: https://example.org -->\n<p>A</p>'), [('https://example.org', '<p>A</p>')])


if __name__ == '__main__':
    unittest.main()
