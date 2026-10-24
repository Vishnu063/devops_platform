import unittest
from app.server import create_app


class EcosystemTests(unittest.TestCase):
    def test_offline_connections_are_explicit_and_do_not_need_a_cluster(self):
        client = create_app().test_client()
        response = client.get('/api/integrations')
        self.assertEqual(200, response.status_code)
        self.assertEqual('disconnected', response.json['kubernetes']['status'])
        self.assertEqual('disconnected', response.json['argocd']['status'])
        self.assertIn(b'disconnected', client.get('/ecosystem').data)
        self.assertIn("default-src 'none'", client.get('/ecosystem').headers['Content-Security-Policy'])
