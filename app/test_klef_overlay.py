"""에듀파인 «바로보기» 조회(core/klef_overlay.py) 시험 — DB 는 가짜 fetch 로 바꾼다."""
import time
import unittest
from unittest import mock

from core import klef_overlay

ROW = {
    'doc_no': '샘플고등학교-13499', 'title': '[안내] 박람회 참석 협조', 'sender': '교육청', 'registered_at': '2026-10-28T08:50:00+09:00',
    'approver_name': '담당', 'body': '본문', 'body_status': 'stored', 'attachments': [{'name': '명단.hwpx'}],
    'meta': {'붙임': ['명단 1부'], '표어': '버림'},
    'official_doc_triage': [
        {'nature': '지침', 'created_at': '2026-10-28T09:00:00', 'result': {'summary': '옛 판정'}},
        {'nature': '참석', 'needs_action': True, 'deadline': '2026-10-28', 'confidence': 0.6, 'created_at': '2026-10-29T09:00:00',
         'result': {'summary': '새 판정', 'obligation': '해당 시', 'work_candidates': [{'name': '외국어', 'why': 'x'}]}},
    ],
    'official_doc_decision': [],
}


class ShapeTest(unittest.TestCase):
    def test_latest_triage_and_trimmed_meta(self):
        doc = klef_overlay.shape(ROW)
        self.assertEqual(doc['triage']['nature'], '참석')
        self.assertEqual(doc['triage']['summary'], '새 판정')
        self.assertEqual(doc['triage']['work_candidates'], [{'name': '외국어', 'why': 'x'}])
        self.assertEqual(doc['attachments'], ['명단.hwpx'])
        self.assertNotIn('표어', doc['meta'])
        self.assertIsNone(doc['decision'])


class LookupTest(unittest.TestCase):
    def run_lookup(self, lookup, items):
        answer = lookup.ask(items)
        ticket = answer.get('ticket')
        for _ in range(200):
            if not ticket:
                return answer
            answer = lookup.poll(ticket)
            if not answer.get('pending'):
                return answer
            time.sleep(0.01)
        self.fail('timeout')

    def test_ticket_then_cache(self):
        calls = []

        def fetch(rows):
            calls.append([r['key'] for r in rows])
            return {r['key']: klef_overlay.shape(ROW) for r in rows if r['no'] == ROW['doc_no']}
        lookup = klef_overlay.DocLookup(fetch=fetch, log=lambda *a: None)
        items = [{'no': ROW['doc_no']}, {'no': '샘플고등학교-1'}, {'no': ROW['doc_no']}]
        first = lookup.ask(items)
        self.assertIn('ticket', first)                       # 처음은 표
        answer = self.run_lookup(lookup, items)
        self.assertEqual(list(answer['docs']), [ROW['doc_no']])
        again = lookup.ask(items)                            # 두 번째는 캐시로 바로
        self.assertEqual(list(again['docs']), [ROW['doc_no']])
        self.assertTrue(all(len(c) == 2 for c in calls))     # 겹친 번호는 한 번만 묻는다

    def test_error_is_friendly_and_not_cached(self):
        def fetch(rows):
            raise klef_overlay.urllib.error.URLError('down')
        lookup = klef_overlay.DocLookup(fetch=fetch, log=lambda *a: None)
        answer = self.run_lookup(lookup, [{'no': 'a-1'}])
        self.assertIn('error', answer)
        self.assertIn('ticket', lookup.ask([{'no': 'a-1'}]))  # 실패는 캐시하지 않는다

    def test_bad_items_ignored(self):
        lookup = klef_overlay.DocLookup(fetch=lambda rows: {}, log=lambda *a: None)
        self.assertEqual(lookup.ask('nope'), {'docs': {}})
        self.assertEqual(lookup.ask([1, None, {'no': ''}]), {'docs': {}})

    def test_title_only_when_unique(self):
        same = dict(ROW, doc_no='x-2')
        with mock.patch.object(klef_overlay, '_rest', side_effect=lambda col, vals: [ROW, same] if col == 'title' else []):
            found = klef_overlay.DocLookup()._fetch_rest([{'no': '', 'title': ROW['title'], 'key': 't:' + ROW['title']}])
        self.assertEqual(found, {})                          # 두 건이 맞으면 고르지 않는다
        with mock.patch.object(klef_overlay, '_rest', side_effect=lambda col, vals: [ROW] if col == 'title' else []):
            found = klef_overlay.DocLookup()._fetch_rest([{'no': '', 'title': ROW['title'], 'key': 't:' + ROW['title']}])
        self.assertEqual(list(found), ['t:' + ROW['title']])

    def test_quote_and_host(self):
        self.assertEqual(klef_overlay._quote('a"b'), '"a\\"b"')
        self.assertTrue(klef_overlay.is_klef('https://klef.jbe.go.kr/bms/x.do'))
        self.assertFalse(klef_overlay.is_klef('https://klef.jbe.go.kr.evil.com/'))
        self.assertIn('__deskKlefDocs', klef_overlay.script())


class SpacePageTest(unittest.TestCase):
    """바로보기에서 데스크가 열어 주는 SPACEKIJUN 주소는 업무노트 한 장·구매 신청 페이지 모양만 (2026-11-12)."""
    W = '/work/o/work/5422ab69-c78b-4c37-adef-87aa8ef525e2'

    def test_only_work_and_purchase_pages(self):
        ok = [self.W, self.W + '?task=ca143aa6-0487-4fe6-8cc9-d52ab82cf4de',
              '/purchase-requests/5422ab69-c78b-4c37-adef-87aa8ef525e2?tab=order']
        bad = ['/work/o/work/x', self.W + '?task=1;alert(1)', 'https://evil.example/', '//evil.example/work/o/work/1',
               '/settings', self.W + '/../../admin', '']
        for route in ok:
            self.assertTrue(klef_overlay.SPACE_PAGE.fullmatch(route), route)
        for route in bad:
            self.assertFalse(klef_overlay.SPACE_PAGE.fullmatch(route), route)

    def test_pages_from_decision_and_meta_are_merged(self):
        work, task = '5422ab69-c78b-4c37-adef-87aa8ef525e2', 'ca143aa6-0487-4fe6-8cc9-d52ab82cf4de'
        found = {'k': {**klef_overlay.shape({'doc_no': 'X-1'}), 'pages': []}}
        raws = {'k': {'official_doc_decision': [{'created_at': '2026-11-12', 'work_id': work, 'task_id': task}]}}

        def fake(table, params):
            if table == 'task' and 'meta->fromOfficialDoc->>doc_no' in params:
                return [{'id': task, 'title': '할 일', 'event_id': work, 'fromOfficialDoc': {'doc_no': 'X-1'}}]
            if table == 'work' and 'id' in params:
                return [{'id': work, 'name': '정보공시'}]
            return []
        with mock.patch.object(klef_overlay, '_get', side_effect=fake):
            klef_overlay._attach_pages(found, raws)
        self.assertEqual(found['k']['pages'], [{'route': f'/work/o/work/{work}?task={task}', 'kind': '할 일', 'title': '할 일', 'parent': '정보공시'}])


class CnsulTest(unittest.TestCase):
    """품의목록 ↔ 구매 신청 품의 차수 (2026-11-12)."""
    PAGE = '5422ab69-c78b-4c37-adef-87aa8ef525e2'

    def test_batch_shape_total_and_route(self):
        shaped = klef_overlay.batch_shape({'id': 'b', 'page_id': self.PAGE, 'title': '1차 품의', 'status': 'submitted',
                                           'purchase_request_pages': {'title': '부품 구매'},
                                           'purchase_order_lines': [{'name': 'A', 'unit_price': 1000, 'qty': 3}, {'name': 'B', 'unit_price': None, 'qty': 1}]})
        self.assertEqual((shaped['total'], shaped['status_label'], shaped['page_title'], shaped['line_count']), (3000, '품의 완료', '부품 구매', 2))
        self.assertEqual(shaped['route'], f'/purchase-requests/{self.PAGE}?tab=order')
        self.assertTrue(klef_overlay.SPACE_PAGE.fullmatch(shaped['route']))
        self.assertEqual(klef_overlay.batch_shape({'page_id': 'x'})['route'], '')

    def test_lookup_by_number_then_title(self):
        calls = []

        def fake(table, params):
            calls.append(params)
            if 'edufine_no' in params:
                return [{'id': 'b1', 'page_id': self.PAGE, 'edufine_no': 'N1'}]
            return [{'id': 'b2', 'page_id': self.PAGE, 'edufine_title': '제목 둘', 'edufine_no': None},
                    {'id': 'b3', 'page_id': self.PAGE, 'edufine_title': '제목 둘', 'edufine_no': 'OTHER'}]
        with mock.patch.object(klef_overlay, '_get', side_effect=fake):
            found = klef_overlay.cnsul_lookup([{'no': 'N1', 'title': '제목 하나'}, {'no': 'N2', 'title': '제목 둘'}])
        self.assertEqual([b['id'] for b in found['N1']], ['b1'])
        self.assertEqual([b['id'] for b in found['N2']], ['b2'])          # 다른 품의번호로 이은 차수는 빼고
        self.assertEqual(len(calls), 2)

    def test_link_rejects_bad_input_before_network(self):
        with mock.patch.object(klef_overlay.urllib.request, 'urlopen') as opened:
            for payload in ({'batch_id': 'x', 'title': 't', 'no': 'N1'}, {'batch_id': self.PAGE, 'title': '', 'no': 'N1'},
                            {'batch_id': self.PAGE, 'title': 't', 'no': 'N1;drop'}, None):
                with self.assertRaises(ValueError):
                    klef_overlay.link_batch(payload)
            opened.assert_not_called()

    def test_jobs_ticket_flow(self):
        jobs = klef_overlay.Jobs(kinds={'ok': lambda p: {'echo': p}, 'bad': lambda p: (_ for _ in ()).throw(PermissionError('권한 없음'))})
        self.assertIn('error', jobs.ask('nope'))
        for kind, want in (('ok', {'result': {'echo': 1}}), ('bad', {'error': '권한 없음'})):
            ticket = jobs.ask(kind, 1)['ticket']
            for _ in range(100):
                answer = jobs.poll(ticket)
                if not answer.get('pending'):
                    break
                time.sleep(0.01)
            self.assertEqual(answer, want)
        self.assertIn('error', jobs.poll('missing'))


if __name__ == '__main__':
    unittest.main()
