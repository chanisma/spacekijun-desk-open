import json
import unittest
from unittest.mock import MagicMock, patch
from urllib.parse import parse_qs, urlparse

from core import notify, supa_auth


class NotificationTargetTests(unittest.TestCase):
    def test_resource_lookup_filters_current_account(self):
        response = MagicMock()
        response.__enter__.return_value.read.return_value = json.dumps([{'resource_id':'mine'}]).encode()
        with patch.object(notify, 'config', return_value={'url':'https://example.test'}), \
             patch.object(supa_auth, 'auth_headers', return_value={}), \
             patch.object(supa_auth, 'load_session', return_value={'user_id':'current-user'}), \
             patch('urllib.request.urlopen', return_value=response) as request:
            self.assertEqual(supa_auth.my_resource_id(), 'mine')
        query = parse_qs(urlparse(request.call_args.args[0].full_url).query)
        self.assertEqual(query['user_id'], ['eq.current-user'])

    def test_signed_in_account_overrides_stale_target_and_errors_do_not_fallback(self):
        cfg = {'resource_id':'wrong-target'}
        with patch.object(supa_auth, 'load_session', return_value={'user_id':'current-user'}), \
             patch.object(supa_auth, 'my_resource_id', return_value='mine'), \
             patch.object(notify, 'save_config'):
            self.assertEqual(notify.resource_id(cfg), 'mine')
        with patch.object(supa_auth, 'load_session', return_value={'user_id':'current-user'}), \
             patch.object(supa_auth, 'my_resource_id', side_effect=supa_auth.AuthError('unavailable')):
            with self.assertRaises(supa_auth.AuthError):
                notify.resource_id({'resource_id':'wrong-target'})
