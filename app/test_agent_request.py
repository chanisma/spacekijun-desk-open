"""에이전트 작업 요청 — 받는 쪽 (2026-11-11). 진짜 서버에는 붙지 않는다."""
from test_sandbox import use_sandbox
use_sandbox()
import unittest
from unittest.mock import patch

from core import agent_request, realtime

RID = '11111111-2222-4333-8444-555555555555'
RECORD = {'id': 'n9', 'type': 'agent_request', 'title': '작업 요청: 협의록 작성', 'message': '11월 협의록',
          'meta': {'request_id': RID, 'sender_name': '김선생', 'batch_id': 'b'}, 'is_read': False}


class AgentRequestTest(unittest.TestCase):
    def test_realtime_listens_to_requests_as_well_as_messages(self):
        filters = [table['filter'] for table in realtime.join_message('t', '1')['payload']['config']['postgres_changes']]
        self.assertEqual(filters, ['type=eq.desk_message', 'type=eq.agent_request'])
        message = {'topic': realtime.TOPIC, 'event': 'postgres_changes',
                   'payload': {'data': {'type': 'INSERT', 'record': RECORD}}}
        self.assertEqual(realtime.record_of(message), RECORD)
        other = {**message, 'payload': {'data': {'type': 'INSERT', 'record': {**RECORD, 'type': 'tama_call'}}}}
        self.assertIsNone(realtime.record_of(other))

    def test_arrived_reads_only_request_notifications_with_a_real_id(self):
        self.assertEqual(agent_request.arrived(RECORD), {'request_id': RID, 'title': '작업 요청: 협의록 작성', 'sender': '김선생'})
        self.assertIsNone(agent_request.arrived({**RECORD, 'type': 'desk_message'}))
        self.assertIsNone(agent_request.arrived({**RECORD, 'meta': {'request_id': 'x; drop'}}))

    def test_prompt_comes_from_the_server_and_ids_are_checked_first(self):
        with patch.object(agent_request.desk_message, '_request') as request:
            with self.assertRaises(ValueError):
                agent_request.prompt('../etc')
            request.assert_not_called()
        answer = {'id': RID, 'title': 't', 'from': '김선생', 'prompt': '[작업 요청] …'}
        with patch.object(agent_request.desk_message, '_request', return_value=answer) as request:
            self.assertEqual(agent_request.prompt(RID.upper())['prompt'], '[작업 요청] …')
            request.assert_called_once_with('POST', 'rpc/agent_request_prompt', body={'p_id': RID})

    def test_mark_handed_says_desk_and_trims(self):
        with patch.object(agent_request.desk_message, '_request', return_value={'status': 'handed'}) as request:
            agent_request.mark_handed(RID, label='PC' * 40, agent='claude-1')
        body = request.call_args.kwargs['body']
        self.assertEqual((body['p_via'], body['p_agent'], len(body['p_label'])), ('desk', 'claude-1', 60))

    def test_inbox_keeps_only_rows(self):
        with patch.object(agent_request.desk_message, '_request', return_value=[{'id': RID}, 'x', {}]):
            self.assertEqual(agent_request.inbox(), [{'id': RID}])
        with patch.object(agent_request.desk_message, '_request', return_value=None):
            self.assertEqual(agent_request.inbox(), [])

    def test_summary_has_no_body(self):
        line = agent_request.summary({'from': '김선생', 'title': '협의록', 'due_date': '2026-11-20', 'body': '비밀'})
        self.assertEqual(line, '김선생 선생님의 작업 요청 «협의록» · 기한 2026-11-20')


if __name__ == '__main__':
    unittest.main()
