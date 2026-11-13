"""NEIS 대화형 이동의 순수 로직 검증 — 브라우저 없이 돈다."""
from test_sandbox import use_sandbox
use_sandbox()          # 진짜 자격증명 파일에는 절대 닿지 않는다
import re
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from core import (neis_actions, neis_assist, neis_glossary, neis_menu, neis_nav,
                  neis_overlay, neis_roles, portal)

INDEX = {'version': neis_menu.CACHE_VERSION, 'at': 0, 'tabs': {
    '교과담임': {'groups': [
        {'group': '학적', 'screens': ['출결관리', '출결현황및통계']},
        {'group': '교육과정', 'screens': ['시간표관리']},
        {'group': '성적', 'screens': ['정기시험', '수행평가', '성적처리']},
    ]},
    '부서장(정보공시)': {'groups': [
        {'group': '{정보공시}학교정보공시', 'screens': ['공시자료관리']},
    ]},
}}


class NoRolesTestCase(unittest.TestCase):
    """정본 파일이 없는 학교를 흉내 낸다 — 긁어 온 색인만으로 돌아야 한다.

    합쳐서 쓰는 쪽은 `RoleMenuTests` 와 `InnerTabRoutingTests` 가 진짜 정본으로 본다.
    """

    def setUp(self):
        self._roles = patch('core.neis_roles.rows', return_value=[])
        self._roles.start()
        self.addCleanup(self._roles.stop)


class MenuIndexTests(NoRolesTestCase):
    def test_crawled_flattens_every_tab_and_group(self):
        names = [s['name'] for s in neis_menu.crawled(INDEX)]
        self.assertIn('출결관리', names)
        self.assertIn('공시자료관리', names)
        self.assertEqual(len(names), 7)

    def test_find_prefers_exact_name_over_substring(self):
        self.assertEqual(neis_menu.find(INDEX, '출결관리')['name'], '출결관리')
        self.assertEqual(neis_menu.find(INDEX, '출결관리')['tab'], '교과담임')

    def test_find_returns_none_for_unknown_screen(self):
        self.assertIsNone(neis_menu.find(INDEX, '존재하지않는화면'))

    def test_outline_lists_screen_with_its_place(self):
        text = neis_menu.outline(neis_menu.crawled(INDEX))
        self.assertIn('출결관리   (교과담임 > 학적)', text)
        self.assertEqual(len(text.splitlines()), 7)

    def test_outline_respects_the_limit(self):
        self.assertEqual(len(neis_menu.outline(neis_menu.crawled(INDEX), limit=2).splitlines()), 2)

    def test_empty_index_is_stale(self):
        self.assertTrue(neis_menu.is_stale(None))
        self.assertTrue(neis_menu.is_stale({'at': 0}))


DEEP = {'version': neis_menu.CACHE_VERSION, 'at': 0, 'tabs': {
    '교과담임': {'groups': [
        {'group': '학적', 'screens': ['출결관리', '출결현황및통계'],
         'children': {'출결관리': ['교과시간별출석부출력', '과목별출결관리'],
                      '출결현황및통계': []}},
    ]},
}}


class DeepIndexTests(NoRolesTestCase):
    """담임 탭은 3단계까지 받아 둔다 — 진짜 기능 이름이 거기 있다."""

    def test_a_folder_is_replaced_by_the_screens_under_it(self):
        names = [s['name'] for s in neis_menu.screens(DEEP)]
        self.assertIn('과목별출결관리', names)
        self.assertIn('교과시간별출석부출력', names)
        self.assertNotIn('출결관리', names)          # 폴더는 고를 대상이 아니다

    def test_a_childless_screen_stays_as_itself(self):
        names = [s['name'] for s in neis_menu.screens(DEEP)]
        self.assertIn('출결현황및통계', names)

    def test_the_chain_carries_the_folder_it_sits_under(self):
        found = neis_menu.find(DEEP, '과목별출결관리')
        self.assertEqual(found['chain'], ['출결관리', '과목별출결관리'])
        self.assertEqual(neis_menu.find(DEEP, '출결현황및통계')['chain'], ['출결현황및통계'])

    def test_outline_shows_where_the_screen_lives(self):
        text = neis_menu.outline(neis_menu.screens(DEEP))
        self.assertIn('과목별출결관리   (교과담임 > 학적 > 출결관리)', text)
        self.assertIn('출결현황및통계   (교과담임 > 학적)', text)

    def test_shallow_index_still_works(self):
        self.assertEqual(neis_menu.find(INDEX, '출결관리')['chain'], ['출결관리'])


class DeepenTabTests(NoRolesTestCase):
    """하위 판정은 누르기 전후의 차이로 한다 — 형제의 하위가 남아 있을 수 있다."""

    def page(self, snapshots):
        page = Mock()
        page.locator.return_value.all_text_contents.return_value = ['교과담임 0단계 메뉴항목']
        page.evaluate.side_effect = list(snapshots)
        return page

    def test_children_of_the_clicked_item_only(self):
        folder = '출결관리 2단계 메뉴항목'
        stale = '다른화면 3단계'            # 앞서 누른 형제의 하위가 아직 남아 있는 상황
        snapshots = [
            ['출결관리 2단계', stale],                       # 누르기 전
            [folder, stale, '과목별출결관리 3단계'],          # 누른 뒤
        ]
        page = self.page(snapshots)
        entry = {'groups': [{'group': '학적', 'screens': ['출결관리']}]}
        with patch.object(neis_nav, 'open_tab'), patch.object(neis_nav, 'click_item'), \
             patch.object(neis_nav, 'close_popups', return_value=0):
            neis_menu.deepen_tab(page, '교과담임', entry)
        self.assertEqual(entry['groups'][0]['children'],
                         {'출결관리': ['과목별출결관리']})

    def test_a_leaf_records_no_children(self):
        page = self.page([['시간표관리 2단계'], ['시간표관리 2단계']])
        entry = {'groups': [{'group': '교육과정', 'screens': ['시간표관리']}]}
        with patch.object(neis_nav, 'open_tab'), patch.object(neis_nav, 'click_item'), \
             patch.object(neis_nav, 'close_popups', return_value=0):
            neis_menu.deepen_tab(page, '교과담임', entry)
        self.assertEqual(entry['groups'][0]['children'], {'시간표관리': []})

    def test_one_broken_item_does_not_lose_the_rest(self):
        """한 항목을 못 눌러도 나머지는 모으고, 못 읽은 항목도 그대로 고를 수 있어야 한다."""
        entry = {'groups': [{'group': '학적', 'screens': ['깨진화면', '시간표관리']}]}
        page = Mock()
        page.locator.return_value.all_text_contents.return_value = ['교과담임 0단계 메뉴항목']
        page.evaluate.side_effect = [[], ['시간표관리 2단계'], ['시간표관리 2단계']]
        with patch.object(neis_nav, 'open_tab'), patch.object(neis_nav, 'close_popups', return_value=0), \
             patch.object(neis_nav, 'click_item', side_effect=[neis_nav.NavError('없음'), None]):
            neis_menu.deepen_tab(page, '교과담임', entry)
        self.assertEqual(entry['groups'][0]['children'], {'시간표관리': []})
        index = {'version': neis_menu.CACHE_VERSION, 'at': 0, 'tabs': {'교과담임': entry}}
        self.assertIn('깨진화면', [s['name'] for s in neis_menu.screens(index)])

    def test_only_priority_tabs_are_deepened(self):
        self.assertIn('교과담임', neis_menu.PRIORITY_TABS)
        self.assertIn('동아리담임', neis_menu.PRIORITY_TABS)
        self.assertNotIn('교육통계', neis_menu.PRIORITY_TABS)


class InterpretTests(NoRolesTestCase):
    """모델 키가 없는 PC 에서도 이름 맞춤만으로 동작해야 한다."""

    def setUp(self):
        super().setUp()
        patcher = patch.object(neis_assist.summarize, 'load_key', return_value=None)
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_attendance_words_reach_the_attendance_screen(self):
        plan = neis_assist.interpret('인공지능 기초 과목 출결해야 해', INDEX)
        self.assertEqual(plan['tab'], '교과담임')
        self.assertIn('출결', plan['screen'])

    def test_exact_screen_name_skips_the_model(self):
        with patch.object(neis_assist, '_ask_model') as model:
            plan = neis_assist.interpret('시간표관리 열어 줘', INDEX)
        model.assert_not_called()
        self.assertEqual(plan['screen'], '시간표관리')
        self.assertEqual(plan['source'], 'name')

    def test_unrelated_request_offers_no_screen(self):
        plan = neis_assist.interpret('점심 메뉴 알려 줘', INDEX)
        self.assertIsNone(plan['screen'])
        self.assertEqual(plan['candidates'], [])

    def test_blank_request_is_rejected(self):
        with self.assertRaises(neis_assist.AssistError):
            neis_assist.interpret('   ', INDEX)

    def test_empty_index_is_rejected(self):
        with self.assertRaises(neis_assist.AssistError):
            neis_assist.interpret('출결', {'tabs': {}})


class DecisionSourceTests(NoRolesTestCase):
    """무엇이 화면을 골랐는지 남긴다 — 사용자가 "AI 가 쓰이긴 하나" 를 확인할 수 있어야 한다."""

    def test_exact_name_is_marked_as_decided_without_the_model(self):
        with patch.object(neis_assist.summarize, 'load_key', return_value='key'), \
             patch.object(neis_assist, '_ask_model') as model:
            plan = neis_assist.interpret('시간표관리', INDEX)
        model.assert_not_called()
        self.assertEqual(plan['source'], 'name')

    def test_a_model_choice_is_marked_as_model(self):
        answer = {'screen': '수행평가', 'reply': '이동'}
        with patch.object(neis_assist.summarize, 'load_key', return_value='key'), \
             patch.object(neis_assist, '_ask_model', return_value=answer):
            plan = neis_assist.interpret('점수 넣어야 해', INDEX)
        self.assertEqual(plan['source'], 'model')

    def test_a_useless_model_answer_is_marked_as_fallback(self):
        with patch.object(neis_assist.summarize, 'load_key', return_value='key'), \
             patch.object(neis_assist, '_ask_model', return_value={'screen': ''}):
            plan = neis_assist.interpret('출결', INDEX)
        self.assertEqual(plan['source'], 'fallback')
        self.assertIsNotNone(plan['screen'])        # 그래도 이름 맞춤으로는 찾아 준다

    def test_no_key_is_marked_as_offline(self):
        with patch.object(neis_assist.summarize, 'load_key', return_value=None):
            self.assertEqual(neis_assist.interpret('출결', INDEX)['source'], 'offline')
            self.assertEqual(neis_assist.interpret('점심 뭐지', INDEX)['source'], 'offline')

    def test_nothing_matches_with_a_working_model(self):
        with patch.object(neis_assist.summarize, 'load_key', return_value='key'), \
             patch.object(neis_assist, '_ask_model', return_value={'screen': ''}):
            self.assertEqual(neis_assist.interpret('점심 뭐지', INDEX)['source'], 'none')


class ModelAnswerTests(NoRolesTestCase):
    def test_invented_screen_name_is_discarded(self):
        """목록에 없는 이름으로 데려가면 안 된다 — 못 찾는 것보다 나쁘다."""
        answer = {'screen': '출결마법사', 'subject': '인공지능 기초', 'reply': '이동합니다'}
        with patch.object(neis_assist, '_ask_model', return_value=answer):
            plan = neis_assist.interpret('인공지능 기초 출결', INDEX)
        self.assertNotEqual(plan['screen'], '출결마법사')
        self.assertIn('출결', plan['screen'])          # 이름 맞춤으로 되돌아온다
        self.assertEqual(plan['subject'], '인공지능 기초')

    def test_model_choice_inside_the_index_is_used(self):
        answer = {'screen': '수행평가', 'subject': '', 'grade': '1', 'room': '5', 'reply': '이동'}
        with patch.object(neis_assist, '_ask_model', return_value=answer):
            plan = neis_assist.interpret('1학년 5반 점수 넣어야 해', INDEX)
        self.assertEqual(plan['screen'], '수행평가')
        self.assertEqual((plan['grade'], plan['room']), ('1', '5'))


class ChooseOptionTests(unittest.TestCase):
    def setUp(self):
        super().setUp()
        patcher = patch.object(neis_assist.summarize, 'load_key', return_value=None)
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_single_option_is_taken(self):
        self.assertEqual(neis_assist.choose_option('아무 말', ['과목별출결관리']), '과목별출결관리')

    def test_subject_wording_picks_the_subject_screen(self):
        picked = neis_assist.choose_option('인공지능 기초 과목 출결해야 해',
                                           ['교과시간별출석부출력', '과목별출결관리'])
        self.assertEqual(picked, '과목별출결관리')

    def test_no_options_returns_none(self):
        self.assertIsNone(neis_assist.choose_option('출결', []))


class RowPatternTests(unittest.TestCase):
    def test_row_text_splits_into_grade_room_subject(self):
        match = neis_actions.ROW_PATTERN.match('1학년 5(인공지능 기초)')
        self.assertEqual(match.groups(), ('1', '5', '인공지능 기초'))

    def test_plain_text_is_not_a_row(self):
        self.assertIsNone(neis_actions.ROW_PATTERN.match('학생수 : 25명'))


class PickRowTests(unittest.TestCase):
    ROWS = ['1학년 5(인공지능 기초)', '1학년 7(인공지능 기초)', '3학년 2(정보)']

    def page(self):
        page = Mock()
        page.evaluate.return_value = self.ROWS
        return page

    def test_ambiguous_subject_is_left_alone(self):
        """맞는 수업이 둘이면 고르지 않는다 — 엉뚱한 반을 열어 두는 것보다 낫다."""
        result = neis_actions.pick_row(self.page(), subject='인공지능 기초')
        self.assertIsNone(result['picked'])
        self.assertEqual(len(result['matches']), 2)

    def test_subject_with_room_picks_one(self):
        page = self.page()
        result = neis_actions.pick_row(page, subject='인공지능 기초', room='7')
        self.assertEqual(result['picked']['text'], '1학년 7(인공지능 기초)')
        page.locator.assert_called()

    def test_spacing_differences_still_match(self):
        page = self.page()
        result = neis_actions.pick_row(page, subject='인공지능기초', room='5')
        self.assertEqual(result['picked']['room'], '5')

    def test_unknown_subject_picks_nothing(self):
        result = neis_actions.pick_row(self.page(), subject='한문')
        self.assertIsNone(result['picked'])
        self.assertEqual(result['matches'], [])
        self.assertEqual(len(result['rows']), 3)

    def test_no_condition_never_picks_silently(self):
        result = neis_actions.pick_row(self.page())
        self.assertIsNone(result['picked'])


class ItemPatternTests(unittest.TestCase):
    def test_leaf_and_folder_labels_both_parse(self):
        leaf = neis_nav.ITEM_PATTERN.match('출결관리 2단계')
        folder = neis_nav.ITEM_PATTERN.match('출결관리 2단계 메뉴항목')
        self.assertEqual(leaf.group(1), '출결관리')
        self.assertIsNone(leaf.group(3))
        self.assertIsNotNone(folder.group(3))

    def test_item_regex_matches_both_labels(self):
        pattern = neis_nav._item_rx('과목별출결관리')
        self.assertTrue(pattern.match('과목별출결관리 3단계'))
        self.assertTrue(pattern.match('과목별출결관리 3단계 메뉴항목'))
        self.assertFalse(pattern.match('과목별출결관리조회 3단계'))

    def test_name_with_regex_characters_is_escaped(self):
        pattern = neis_nav._item_rx('성적/학습분석자료조회')
        self.assertTrue(pattern.match('성적/학습분석자료조회 2단계'))

    def test_tabs_strip_the_level_suffix(self):
        page = Mock()
        page.locator.return_value.all_text_contents.return_value = [
            '교과담임 0단계 메뉴항목', '교육통계 0단계 메뉴항목']
        self.assertEqual(neis_nav.tabs(page), ['교과담임', '교육통계'])


class GlossaryTests(unittest.TestCase):
    """화면 이름은 업무 용어라 교사가 쓰는 말과 다르다. 그 틈을 사전이 메운다."""

    def index(self):
        """사전에 있는 화면만으로 만든 색인. 실제 색인과 같은 모양이다."""
        groups = {}
        for name in neis_glossary.SCREENS:
            groups.setdefault('묶음', []).append(name)
        return {'version': neis_menu.CACHE_VERSION, 'at': 0,
                'tabs': {'교과담임': {'groups': [{'group': '묶음', 'screens': groups['묶음']}]}}}

    def setUp(self):
        super().setUp()
        patcher = patch.object(neis_assist.summarize, 'load_key', return_value=None)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.built = self.index()

    def pick(self, utterance):
        return neis_assist.interpret(utterance, self.built)['screen']

    def test_teacher_slang_reaches_the_right_screen(self):
        cases = {
            '세특 써야 해': '과목별세부능력및특기사항',
            '수행평가 채점해야 해': '수행평가채점',
            '출석부 뽑아야 해': '교과시간별출석부출력',
            '관찰 기록 남겨야지': '관찰내용관리',
            '독서활동 입력': '과목별독서활동',
            '문항 난이도 입력': '문항정보표관리',
        }
        for utterance, expected in cases.items():
            self.assertEqual(self.pick(utterance), expected, utterance)

    def test_a_longer_word_wins_over_a_shorter_one(self):
        """`출석부` 가 `출석` 을 이겨야 출석부 출력 화면으로 간다."""
        self.assertEqual(self.pick('출석부'), '교과시간별출석부출력')
        self.assertEqual(self.pick('출석 처리'), '과목별출결관리')

    def test_every_entry_has_a_sentence_and_at_least_one_word(self):
        for name, (text, words) in neis_glossary.SCREENS.items():
            self.assertTrue(text.strip(), name)
            self.assertTrue(words, name)
            self.assertNotIn('\n', text, name)

    def test_unknown_screen_has_no_label(self):
        self.assertEqual(neis_glossary.label('없는화면'), '')
        self.assertEqual(neis_glossary.words('없는화면'), ())

    def test_outline_carries_the_purpose_to_the_model(self):
        text = neis_menu.outline(neis_menu.screens(DEEP))
        self.assertIn('— 내 수업의 날짜별 출결', text)


MANUAL = {
    '학교일지관리': {'key': '교무학사(고)›교육과정›학교일지관리›학교일지관리',
                     'purpose': '날짜별 학교일지를 만들고 수업일수 누계를 확인한다.',
                     'before': ['「학사일정관리」에서 연간 학사일정을 등록한다'], 'guide': True},
    '경영현황': {'key': '교무학사(고)›경영지원›경영지원›경영현황',
                 'purpose': '경영 현황을 조회함.', 'before': ['학교생활기록부 전체를 마감함'], 'guide': False},
    # 손으로 쓴 SCREENS 에 이미 있는 화면
    '과목별출결관리': {'purpose': '설명서 문장', 'before': ['출결 선행'], 'guide': True},
}


class ManualKnowledgeTests(unittest.TestCase):
    """나이스 사용자 설명서에서 온 지식 — 손으로 쓴 설명이 없는 화면을 채운다 (2026-10-11)."""

    def setUp(self):
        patcher = patch.object(neis_glossary, 'manual', return_value=MANUAL)
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_manual_fills_screens_with_no_hand_written_entry(self):
        self.assertEqual(neis_glossary.describe('학교일지관리'), '날짜별 학교일지를 만들고 수업일수 누계를 확인한다.')

    def test_hand_written_entry_wins(self):
        """교사가 쓰는 말로 다듬은 설명이 먼저다 — 설명서 문장은 공문체다."""
        self.assertNotEqual(neis_glossary.describe('과목별출결관리'), '설명서 문장')

    def test_briefing_says_what_must_be_done_first(self):
        self.assertEqual(neis_glossary.briefing('학교일지관리'),
                         '먼저 끝나 있어야 할 일: 「학사일정관리」에서 연간 학사일정을 등록한다')

    def test_briefing_stays_quiet_without_a_curated_guide(self):
        """절 머리글의 선행처리는 절 전체 기준이라 이 화면과 어긋나기도 한다 — 다듬은 안내에서만 말한다."""
        self.assertEqual(neis_glossary.briefing('경영현황'), '')
        self.assertEqual(neis_glossary.briefing('없는화면'), '')

    def test_outline_carries_manual_purpose_to_the_model(self):
        self.assertIn('수업일수 누계', neis_glossary.label('학교일지관리'))


class ManualResourceTests(unittest.TestCase):
    """번들에 들어가는 실제 파일 — 없어도 앱은 돌지만, 있으면 모양이 맞아야 한다."""

    def test_resource_shape(self):
        data = neis_glossary.manual()
        if not data:
            self.skipTest('neis-manual.json 없음 — scripts/build-neis-manual.py')
        self.assertGreater(len(data), 150)
        for name, entry in data.items():
            self.assertTrue(entry.get('purpose'), name)
            self.assertIsInstance(entry.get('before', []), list, name)
        # 설명서는 «지필평가», 메뉴는 «정기시험» — 정기시험 화면이 이어져 있어야 한다
        self.assertIn('정기시험성적관리', data)


CAPTURED = {'동아리활동관리': {
    'name': '동아리활동관리',
    'tabs': ['부서만들기', '부서배정', '이수시간기준등록', '동아리활동 출결관리', '동아리활동관리'],
    'fields': ['필수입력학년도', '필수입력부서명', '두잇(코딩)'],
    'actions': ['조회', '담당교사일괄변경', '저장'],
    'columns': ['순번', '시간표 일자', '교시'],
    'text': ['Total 0', '담당교사일괄변경'],
}}


class CapturedKnowledgeTests(unittest.TestCase):
    """화면 안쪽까지 안다 — 한 화면 안에 또 다른 탭이 있는 경우가 많다."""

    def setUp(self):
        patcher = patch.object(neis_glossary, 'captured', return_value=CAPTURED)
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_inner_tabs_are_known(self):
        self.assertEqual(neis_glossary.inner_tabs('동아리활동관리')[:2], ('부서만들기', '부서배정'))
        self.assertEqual(neis_glossary.inner_tabs('없는화면'), ())

    def test_inner_tabs_also_come_from_the_authoritative_list(self):
        """화면을 열어 보지 않은 곳의 안쪽 탭은 업무분장 메뉴목록에만 있다."""
        self.assertIn('일일출결관리(담임용)', neis_glossary.inner_tabs('출결관리'))

    def test_label_shows_the_inner_tabs_to_the_model(self):
        label = neis_glossary.label('동아리활동관리')
        self.assertIn('화면 안 탭: 부서만들기 / 부서배정', label)
        self.assertIn('동아리 활동 내용', label)          # 손으로 쓴 설명도 남는다

    def test_content_words_gather_what_is_on_the_screen(self):
        found = neis_glossary.content_words('동아리활동관리')
        self.assertIn('부서배정', found)
        self.assertIn('담당교사일괄변경', found)
        self.assertIn('학년도', found)                   # '필수입력' 은 떼고 넣는다
        self.assertNotIn('필수입력학년도', found)

    def test_a_screen_with_no_capture_says_nothing(self):
        self.assertEqual(neis_glossary.content_words('없는화면'), ())
        self.assertEqual(neis_glossary.label('없는화면'), '')

    def test_words_inside_the_screen_pull_it_up_the_list(self):
        screens = [{'name': '동아리활동관리', 'tab': '동아리담임', 'group': '학생생활'},
                   {'name': '동아리활동부서반별이수시간조회', 'tab': '동아리담임', 'group': '학생생활'}]
        ranked = neis_assist.match_by_name('동아리 부서배정 해야 해', screens)
        self.assertEqual(ranked[0]['name'], '동아리활동관리')


class ChooseInnerTabTests(unittest.TestCase):
    TABS = ('부서만들기', '부서배정', '이수시간기준등록', '동아리활동 출결관리', '동아리활동관리')

    def test_a_tab_named_in_the_request_is_taken(self):
        self.assertEqual(neis_assist.choose_inner_tab('동아리 부서배정 해야 해', self.TABS), '부서배정')

    def test_spacing_does_not_matter(self):
        self.assertEqual(neis_assist.choose_inner_tab('이수시간 기준 등록', self.TABS), '이수시간기준등록')

    def test_the_longer_match_wins(self):
        """`동아리활동관리` 와 `동아리활동 출결관리` 가 함께 걸리면 더 구체적인 쪽."""
        self.assertEqual(neis_assist.choose_inner_tab('동아리활동 출결관리 하려고', self.TABS),
                         '동아리활동 출결관리')

    def test_a_part_of_a_long_tab_name_is_enough(self):
        """탭 이름을 통째로 말하는 사람은 없다."""
        tabs = ('최소성취수준보장지도(추가학습)대상자', '최소성취수준보장지도(추가학습)예외처리',
                '최소성취수준보장지도(추가학습)마감')
        self.assertEqual(neis_assist.choose_inner_tab('추가학습 예외처리 하려고', tabs),
                         '최소성취수준보장지도(추가학습)예외처리')

    def test_a_trailing_word_may_be_left_out(self):
        tabs = ('결시생 인정점 관리', '과목별 성적산출')
        self.assertEqual(neis_assist.choose_inner_tab('결시생 인정점', tabs), '결시생 인정점 관리')

    def test_a_short_or_tied_match_is_not_taken(self):
        """짧게 걸리거나 두 탭이 비슷하면 고르지 않는다 — 화면을 함부로 바꾸지 않는다."""
        self.assertEqual(neis_assist.choose_inner_tab('동아리 기록', self.TABS), '')
        self.assertEqual(neis_assist.choose_inner_tab('관리', ('가관리', '나관리')), '')

    def test_brackets_and_dots_are_ignored(self):
        """탭 이름에는 괄호가 흔하다. 사람은 그렇게 말하지 않는다."""
        tabs = ('성취기준관리', '성취수준(평가기준)관리')
        self.assertEqual(neis_assist.choose_inner_tab('성취수준 평가기준 관리', tabs),
                         '성취수준(평가기준)관리')

    def test_nothing_is_guessed(self):
        """말에 없는 탭을 눌러 화면을 바꾸면 사용자가 헷갈린다."""
        self.assertEqual(neis_assist.choose_inner_tab('동아리 기록', self.TABS), '')
        self.assertEqual(neis_assist.choose_inner_tab('부서배정', ()), '')


class ClickTabTests(unittest.TestCase):
    def button(self, count=1, klass=''):
        page = Mock()
        target = page.locator.return_value.filter.return_value.first
        target.count.return_value = count
        target.get_attribute.return_value = klass
        return page, target

    def test_a_live_tab_is_clicked(self):
        page, target = self.button(klass='cl-control cl-button')
        self.assertTrue(neis_actions.click_tab(page, '부서배정')['clicked'])
        target.click.assert_called_once()

    def test_a_greyed_out_tab_is_reported_not_clicked(self):
        """권한이 없으면 회색이 된다. 눌러도 아무 일이 없으므로 미리 가려낸다."""
        page, target = self.button(klass='cl-control cl-button cl-disabled')
        answer = neis_actions.click_tab(page, '부서만들기')
        self.assertFalse(answer['clicked'])
        self.assertIn('쓸 수 없는', answer['why'])
        target.click.assert_not_called()

    def test_a_missing_tab_is_reported(self):
        page, _ = self.button(count=0)
        self.assertFalse(neis_actions.click_tab(page, '없는탭')['clicked'])


class DismissDialogTests(unittest.TestCase):
    """화면에 들어가기만 해도 뜨는 알림이 있다. 안 치우면 이후 클릭이 전부 막힌다."""

    def page(self, labels):
        """단추 라벨 목록을 가진 모달 하나가 떠 있는 화면."""
        page = Mock()
        dialogs = Mock()
        dialogs.count.side_effect = [1, 0]
        clicked = []

        def locator(_selector):
            found = Mock()

            def filtered(has_text=None):
                target = Mock()
                label = next((l for l in labels if has_text.match(l)), None)
                target.first.count.return_value = 1 if label else 0
                target.first.click.side_effect = lambda **_: clicked.append(label)
                return target
            found.filter.side_effect = filtered
            return found

        dialogs.last.locator.side_effect = locator
        dialogs.last.text_content.return_value = '알림 ' + ' '.join(labels)
        page.locator.return_value = dialogs
        return page, clicked

    def test_a_plain_notice_is_acknowledged(self):
        page, clicked = self.page(['확인'])
        self.assertEqual(neis_nav.dismiss_dialogs(page), 1)
        self.assertEqual(clicked, ['확인'])

    def test_a_question_is_cancelled_not_confirmed(self):
        """무엇을 묻는지 모르는 채로 확인을 누르면 지우거나 마감할 수 있다."""
        page, clicked = self.page(['확인', '취소'])
        neis_nav.dismiss_dialogs(page)
        self.assertEqual(clicked, ['취소'])

    def test_yes_no_takes_the_no(self):
        page, clicked = self.page(['예', '아니오'])
        neis_nav.dismiss_dialogs(page)
        self.assertEqual(clicked, ['아니오'])

    def test_an_unfamiliar_dialog_is_left_alone(self):
        page, clicked = self.page(['삭제', '저장'])
        self.assertEqual(neis_nav.dismiss_dialogs(page), 0)
        self.assertEqual(clicked, [])

    def test_nothing_to_do_when_no_dialog_is_open(self):
        page = Mock()
        page.locator.return_value.count.return_value = 0
        self.assertEqual(neis_nav.dismiss_dialogs(page), 0)

    def test_a_second_factor_dialog_is_left_for_the_person(self):
        """닫으면 화면까지 같이 닫힌다. 인증은 사람이 해야 한다."""
        page, clicked = self.page(['닫기'])
        page.locator.return_value.last.text_content.return_value = (
            '2차인증 M-OTP ARS OTP 번호를 입력하세요 인증요청 닫기')
        self.assertEqual(neis_nav.dismiss_dialogs(page), 0)
        self.assertEqual(clicked, [])

    def test_safe_order_puts_confirm_last(self):
        self.assertEqual(neis_nav.DISMISS_ORDER[-1], '확인')
        self.assertEqual(neis_nav.DISMISS_ORDER[0], '취소')


class OverlayInstallTests(unittest.TestCase):
    """나이스 화면에 심는 패널 — 다리를 어떻게 거는지만 확인한다(화면 동작은 node 테스트)."""

    def setUp(self):
        self.enqueued = []
        self.polled = []
        self.page = Mock()
        self.page.context.pages = [self.page]

    def install(self):
        neis_overlay.install(self.page,
                             lambda kind, payload: self.enqueued.append((kind, payload)) or 'job-1',
                             lambda ticket: self.polled.append(ticket) or {'state': 'pending'})
        return {call.args[0]: call.args[1]
                for call in self.page.expose_function.call_args_list}

    def test_the_bridges_are_exposed_on_this_tab_only(self):
        """창을 여러 업무시스템이 함께 쓰므로, 창 전체에 걸면 다른 탭까지 물든다."""
        bridge = self.install()
        self.page.context.expose_function.assert_not_called()
        self.page.context.add_init_script.assert_not_called()
        self.assertEqual(set(bridge), {'__deskAsk', '__deskPick', '__deskPoll', '__deskState'})

    def test_state_bridge_is_harmless_when_not_given(self):
        bridge = self.install()
        self.assertEqual(bridge['__deskState'](), {})

    def test_script_is_installed_for_future_and_current_documents(self):
        self.install()
        source = self.page.add_init_script.call_args.args[0]
        self.assertIn('__deskPoll', source)
        self.page.evaluate.assert_called_once_with(source)

    def test_asking_and_picking_reach_the_queue_as_different_jobs(self):
        bridge = self.install()
        self.assertEqual(bridge['__deskAsk']('출결'), 'job-1')
        self.assertEqual(bridge['__deskPick']('1학년 7(인공지능 기초)'), 'job-1')
        self.assertEqual(self.enqueued,
                         [('assist', {'text': '출결'}),
                          ('pick', {'row': '1학년 7(인공지능 기초)'})])

    def test_polling_passes_the_ticket_through(self):
        bridge = self.install()
        self.assertEqual(bridge['__deskPoll']('job-9'), {'state': 'pending'})
        self.assertEqual(self.polled, ['job-9'])

    def test_reinstall_on_an_already_wired_window_still_injects(self):
        """창을 다시 열면 바인딩이 이미 있다. 그 오류로 주입까지 멈추면 안 된다."""
        self.page.expose_function.side_effect = Exception('already registered')
        neis_overlay.install(self.page, lambda *_: 'job-1', lambda _: {})
        self.page.add_init_script.assert_called_once()

    def test_a_broken_page_does_not_stop_the_install(self):
        self.page.evaluate.side_effect = Exception('page is navigating')
        neis_overlay.install(self.page, lambda *_: 'job-1', lambda _: {})
        self.page.add_init_script.assert_called_once()

    def test_panel_source_is_readable_and_guards_frames(self):
        source = neis_overlay.script()
        self.assertIn('window.top !== window', source)      # 프레임 안에는 만들지 않는다
        self.assertIn('__deskPanel', source)                # 두 번 심지 않는다

    def test_reload_stops_the_old_panel_before_planting_a_new_one(self):
        """그냥 지우면 패널이 켜 둔 재부착 타이머가 도로 붙여 놓는다."""
        source = neis_overlay.reload(self.page)
        calls = [call.args[0] for call in self.page.evaluate.call_args_list]
        self.assertIn('__deskPanelStop', calls[0])
        self.assertEqual(calls[1], source)

    def test_the_panel_offers_a_way_to_be_removed(self):
        self.assertIn('__deskPanelStop', neis_overlay.script())


class DevProfileTests(unittest.TestCase):
    """개발 중에는 데스크를 켜 둔 채로 또 띄운다 — 프로필이 겹치면 잠금이 충돌한다."""

    def folder(self, **kwargs):
        playwright = Mock()
        with patch('core.portal.os.makedirs'):
            portal.launch(playwright, **kwargs)
        return Path(playwright.chromium.launch_persistent_context.call_args.args[0]).name

    def test_default_profile_is_unchanged(self):
        self.assertEqual(self.folder(target='neis'), 'browser-msedge')

    def test_named_profile_gets_its_own_folder(self):
        self.assertEqual(self.folder(target='neis', profile='dev'), 'browser-msedge-dev')

    def test_profile_name_cannot_escape_the_data_directory(self):
        self.assertEqual(self.folder(target='neis', profile='../../etc'), 'browser-msedge-etc')

    def test_a_profile_of_only_punctuation_still_gets_a_folder(self):
        self.assertEqual(self.folder(target='neis', profile='///'), 'browser-msedge-alt')

    def test_unsupported_target_is_still_refused(self):
        with self.assertRaises(ValueError):
            portal.launch(Mock(), target='dev')


class WindowSizeTests(unittest.TestCase):
    """업무시스템 화면은 가로로 길다. 뷰포트를 고정하면 잘려 보인다 (2026-09-11 사용자 보고)."""

    def options(self, **kwargs):
        playwright = Mock()
        with patch('core.portal.os.makedirs'):
            portal.launch(playwright, **kwargs)
        return playwright.chromium.launch_persistent_context.call_args.kwargs

    def test_window_is_maximized_and_follows_the_window_size(self):
        options = self.options(target='neis')
        self.assertTrue(options['no_viewport'])
        self.assertNotIn('viewport', options)
        self.assertIn('--start-maximized', options['args'])

    def test_an_explicit_size_is_still_honoured(self):
        options = self.options(target='neis', viewport=(1280, 800))
        self.assertEqual(options['viewport'], {'width': 1280, 'height': 800})
        self.assertNotIn('no_viewport', options)

    def test_every_target_gets_the_same_treatment(self):
        for target in ('neis', 'eduptl', 'klef'):
            self.assertTrue(self.options(target=target)['no_viewport'], target)


class GotoGuardTests(unittest.TestCase):
    def test_missing_tab_names_the_available_ones(self):
        page = Mock()
        page.locator.return_value.all_text_contents.return_value = ['교과담임 0단계 메뉴항목']
        page.evaluate.return_value = []
        with self.assertRaises(neis_nav.NavError) as caught:
            neis_nav.open_tab(page, '없는탭')
        self.assertIn('교과담임', str(caught.exception))

    def test_empty_chain_is_rejected(self):
        with self.assertRaises(neis_nav.NavError):
            neis_nav.goto(Mock(), '교과담임', [])


if __name__ == '__main__':
    unittest.main()


class RoleMenuTests(unittest.TestCase):
    """업무분장 메뉴목록에서 옮겨 온 정본 — `app/resources/neis-menu-roles.json`."""

    def test_the_authoritative_list_is_present_and_shaped(self):
        rows = neis_roles.rows()
        self.assertGreater(len(rows), 100)
        for row in rows:
            self.assertTrue(row['name'])
            self.assertTrue(row['tabs'], f"{row['name']} 에 역할이 없다")
            for tab in row['tabs']:
                self.assertIn(tab, neis_menu.NAVIGABLE_TABS)

    def test_a_screen_carries_the_path_the_menu_search_shows(self):
        item = neis_roles.find('과목별출결관리', ['교과담임'])
        self.assertEqual(neis_menu.full_path(item),
                         '교과담임 > 학적 > 출결관리 > 과목별출결관리')

    def test_tabs_the_account_lacks_are_left_out(self):
        names = [s['name'] for s in neis_roles.screens(['교과담임'])]
        self.assertIn('과목별출결관리', names)
        self.assertNotIn('출결관리', names)          # 학급담임 것
        self.assertEqual(neis_roles.screens([]), [])

    def test_a_screen_shows_up_for_the_role_that_owns_one_of_its_inner_tabs(self):
        """`동아리활동관리` 줄 자체에는 역할이 없다. 안쪽 탭 셋이 역할을 나눠 갖는다."""
        self.assertEqual(neis_roles.tabs_of('동아리활동관리'), ('학급담임', '동아리담임'))

    def test_inner_tabs_are_filtered_by_role(self):
        self.assertEqual(neis_roles.inner_tabs('동아리활동관리', ['동아리담임']),
                         ('동아리활동 출결관리', '이수시간기준등록', '동아리활동관리'))
        self.assertIn('부서배정', neis_roles.inner_tabs('동아리활동관리', ['학급담임']))

    def test_elsewhere_names_the_role_that_does_have_it(self):
        """이 계정에 없는 역할만 짚는다. 같은 화면이 두 역할에 걸쳐 있는 일이 흔하다."""
        self.assertEqual(neis_roles.elsewhere('출결관리', ['교과담임', '동아리담임']),
                         ('학급담임',))
        self.assertEqual(neis_roles.elsewhere('과목별출결관리', ['교과담임', '학급담임']), ())
        self.assertEqual(neis_roles.elsewhere('없는화면', ['교과담임']), ())


    def test_screens_takes_the_authoritative_list_for_tabs_it_covers(self):
        """정본이 아는 탭은 정본대로. 긁어 온 폴더 이름(`출결관리`)은 섞지 않는다."""
        names = [s['name'] for s in neis_menu.screens(INDEX)]
        self.assertIn('과목별출결관리', names)          # 긁은 색인에는 없던 3단계 화면
        self.assertIn('과목별세부능력및특기사항', names)
        self.assertNotIn('출결관리', names)             # 폴더일 뿐이다

    def test_screens_leave_out_tabs_the_account_does_not_have(self):
        items = neis_menu.screens(INDEX)
        self.assertEqual({i['tab'] for i in items}, {'교과담임', '부서장(정보공시)'})
        self.assertNotIn('출석부출력(담임용)', [i['name'] for i in items])   # 학급담임 것

    def test_screens_keep_what_the_crawl_found_where_the_list_says_nothing(self):
        """정본은 담임 탭만 안다. 그 밖의 탭은 긁어 온 것이 유일한 앎이다."""
        self.assertIn('공시자료관리', [s['name'] for s in neis_menu.screens(INDEX)])

    def test_a_covered_tab_is_not_crawled_three_levels_deep_again(self):
        """정본이 아는 탭을 다시 훑으면 탭마다 20~30초를 버린다."""
        with patch('core.neis_menu.read_tab', return_value={'groups': []}),              patch('core.neis_menu.deepen_tab') as deepen,              patch('core.neis_menu.save'),              patch('core.neis_nav.close_popups'),              patch('core.neis_nav.tabs', return_value=['교과담임']):
            neis_menu.build(Mock(), 'teacher')
        deepen.assert_not_called()

    def test_a_missing_file_does_not_break_anything(self):
        with patch('core.neis_roles._resource_dir', return_value=Path('없는곳')):
            neis_roles._cache = None
            try:
                self.assertEqual(neis_roles.rows(), [])
                self.assertEqual(neis_roles.screens(['교과담임']), [])
            finally:
                neis_roles._cache = None


ACCOUNT = {'version': neis_menu.CACHE_VERSION, 'at': 0,
           'present': ['교과담임', '동아리담임'], 'tabs': {'교과담임': {'groups': []}}}


class InnerTabRoutingTests(unittest.TestCase):
    """화면 안쪽 탭 이름으로 말해도 그 탭이 든 화면으로 가야 한다.

    2026-09-11 사용자 보고: "동아리활동 출결관리" 라고 했더니 들어갈 수도 없는
    부서장(나이스부) 메뉴를 답으로 내놓았다.
    """

    def plan(self, text):
        return neis_assist.interpret(text, ACCOUNT)

    def test_an_inner_tab_name_reaches_the_screen_that_holds_it(self):
        answer = self.plan('동아리활동 출결관리')
        self.assertEqual(answer['screen'], '동아리활동관리')
        self.assertEqual(answer['tab'], '동아리담임')
        self.assertEqual(answer['source'], 'name')       # 모델을 부르지 않는다

    def test_it_never_routes_to_a_tab_the_account_does_not_have(self):
        for text in ('담임 출결', '동아리활동 출결관리', '출결관리', '부서배정'):
            answer = self.plan(text)
            if answer['tab']:
                self.assertIn(answer['tab'], ('교과담임', '동아리담임'), text)

    def test_a_screen_name_beats_the_same_name_used_as_an_inner_tab(self):
        """`과목별세부능력및특기사항` 은 화면이면서 `학기말성적조회` 안쪽 탭이기도 하다."""
        self.assertEqual(self.plan('과목별세부능력및특기사항')['screen'],
                         '과목별세부능력및특기사항')

    def test_a_partly_spoken_inner_tab_still_lands(self):
        self.assertEqual(self.plan('추가학습 예외처리 해야 해')['screen'],
                         '최소성취수준보장지도(추가학습)이수관리')

    def test_two_screens_with_the_same_inner_tab_are_asked_about(self):
        """`정기시험성적집계표` 는 정기시험통계에도 학기말성적조회에도 있다. 찍지 않는다."""
        answer = self.plan('정기시험성적집계표')
        self.assertEqual(answer['source'], 'ask')
        self.assertIsNone(answer['screen'])
        self.assertEqual(set(answer['candidates']), {'정기시험통계', '학기말성적조회'})
        self.assertIn('어느 화면인가요', answer['reply'])

    def test_every_screen_name_finds_its_own_screen(self):
        for item in neis_menu.screens(ACCOUNT):
            self.assertEqual(self.plan(item['name'])['screen'], item['name'])


class OutOfReachTests(unittest.TestCase):
    """이 계정에 없는 담임 역할의 메뉴를 말했을 때 그렇다고 말해 줄 수 있어야 한다."""

    MINE = ['교과담임', '동아리담임']

    def said(self, text):
        return neis_assist.out_of_reach(text, self.MINE)

    def test_a_screen_of_another_role_is_named(self):
        spot = self.said('행동특성및종합의견 써야 해')
        self.assertEqual(spot['said'], '행동특성및종합의견')
        self.assertEqual(spot['tabs'], ('학급담임',))

    def test_an_inner_tab_of_another_role_names_the_screen_it_sits_in(self):
        spot = self.said('일일출결관리 해야 해')
        self.assertEqual(spot['said'], '일일출결관리(담임용)')
        self.assertEqual(spot['screen'], '출결관리')       # 학급담임 화면 안쪽 탭이다
        self.assertEqual(spot['tabs'], ('학급담임',))

    def test_a_partly_spoken_name_still_counts(self):
        self.assertEqual(self.said('반별월출결마감')['said'], '반별월출결마감관리')

    def test_nothing_is_said_when_the_account_can_reach_it(self):
        for text in ('과목별출결관리', '세특 써야 해', '동아리활동 출결관리', '수행평가 점수 입력'):
            self.assertIsNone(self.said(text), text)

    def test_a_few_letters_in_common_are_not_enough_to_claim_it_is_missing(self):
        """`인공지능 기초 과목 출결` 의 '과목출결' 넉 자로 학급담임 화면을 들먹이면 안 된다."""
        self.assertIsNone(self.said('인공지능 기초 과목 출결을 해야해'))
        self.assertIsNone(self.said('1학년 3반 출결 마감'))

    def test_an_account_with_every_role_is_never_warned(self):
        everything = ['교과담임', '학급담임', '동아리담임']
        self.assertIsNone(neis_assist.out_of_reach('일일출결관리', everything))


class ReadDateTests(unittest.TestCase):
    """말 속의 날짜 읽기. 화면에 일자 칸이 있으면 거기까지 맞춰 주려는 것이다."""

    TODAY = __import__('datetime').date(2026, 9, 11)      # 금요일

    def read(self, text):
        return neis_assist.read_date(text, self.TODAY)

    def test_month_and_day_use_this_year(self):
        self.assertEqual(self.read('9월 11일 인공지능 기초 출결'), '2026-09-11')
        self.assertEqual(self.read('9월11일 출결'), '2026-09-11')

    def test_a_full_date_is_taken_as_said(self):
        for text in ('2026-09-10 출결', '2026.09.10 출결', '2026년 9월 10일 출결'):
            self.assertEqual(self.read(text), '2026-09-10', text)

    def test_slash_and_bare_day_are_read(self):
        self.assertEqual(self.read('9/10 출결'), '2026-09-10')
        self.assertEqual(self.read('10일 출결'), '2026-09-10')      # 이번 달

    def test_relative_words(self):
        self.assertEqual(self.read('어제 출결'), '2026-09-10')
        self.assertEqual(self.read('오늘 출결'), '2026-09-11')
        self.assertEqual(self.read('내일 시간표'), '2026-09-12')

    def test_a_day_that_is_not_on_the_calendar_is_refused(self):
        self.assertEqual(self.read('2월 30일 출결'), '')
        self.assertEqual(self.read('13월 5일 출결'), '')

    def test_numbers_that_are_not_dates_are_left_alone(self):
        """`1학년 7반`, `3일간`, `일자순` 에 걸리면 엉뚱한 날을 조회한다."""
        for text in ('1학년 7반 인공지능 기초 출결', '인공지능 기초 과목 출결을 해야해',
                     '3일간 결석', '일자순으로 보자', '세특 써야 해', '2교시 수업'):
            self.assertEqual(self.read(text), '', text)

    def test_screen_date_is_the_shape_neis_wants(self):
        self.assertEqual(neis_assist.screen_date('2026-09-11'), '2026.09.11.')
        self.assertEqual(neis_assist.screen_date('2026-9-1'), '')     # 자리수가 틀리면 버린다
        self.assertEqual(neis_assist.screen_date(''), '')

    def test_the_plan_carries_the_date(self):
        plan = neis_assist.interpret('9월 10일 인공지능 기초 출결', ACCOUNT)
        self.assertEqual(plan['date'], '2026-09-10' if self.TODAY.year == 2026 else plan['date'])
        self.assertEqual(plan['screen'], '과목별출결관리')

    def test_the_regex_wins_over_a_model_that_invents_a_year(self):
        with patch.object(neis_assist, '_ask_model',
                          return_value={'screen': '과목별출결관리', 'date': '2019-01-01'}):
            plan = neis_assist.interpret('9월 10일 출결 해야 해', ACCOUNT)
        self.assertTrue(plan['date'].endswith('-09-10'))

    def test_the_model_date_is_used_when_the_words_are_unreadable(self):
        with patch.object(neis_assist, '_ask_model',
                          return_value={'screen': '과목별출결관리', 'date': '2026-09-04'}):
            plan = neis_assist.interpret('지난주 금요일 출결', ACCOUNT)
        self.assertEqual(plan['date'], '2026-09-04')

    def test_a_malformed_model_date_is_thrown_away(self):
        with patch.object(neis_assist, '_ask_model',
                          return_value={'screen': '과목별출결관리', 'date': '작년 어느 날'}):
            plan = neis_assist.interpret('지난주 금요일 출결', ACCOUNT)
        self.assertEqual(plan['date'], '')


class SetDateTests(unittest.TestCase):
    """일자 칸 채우기. 위젯이 되돌려 놓는 일이 있어 넣은 뒤 반드시 다시 읽는다."""

    def page(self, boxes=1, after='2026.09.10.(목)', locked=0):
        page = Mock()
        page.evaluate.return_value = {'found': boxes, 'locked': locked}
        handle = Mock()
        handle.get_attribute.return_value = '일자'
        handle.input_value.return_value = after
        page.locator.return_value = handle
        return page, handle

    def test_typing_goes_in_character_by_character_then_enter(self):
        """`fill` 은 위젯이 무시한다. 점까지 한 글자씩 친 뒤 Enter 라야 확정된다."""
        page, handle = self.page()
        with patch('core.neis_nav.wait_loading'):
            result = neis_actions.set_date(page, '2026.09.10.')
        self.assertEqual(len(result['set']), 1)
        self.assertEqual(result['set'][0]['value'], '2026.09.10.(목)')
        handle.fill.assert_not_called()
        page.keyboard.type.assert_called_once()
        self.assertEqual(page.keyboard.type.call_args.args[0], '2026.09.10.')
        page.keyboard.press.assert_any_call('Enter')

    def test_a_widget_that_snaps_back_is_reported_not_ignored(self):
        page, _ = self.page(after='2026.09.11.(금)')
        with patch('core.neis_nav.wait_loading'):
            result = neis_actions.set_date(page, '2026.09.10.')
        self.assertEqual(result['set'], [])
        self.assertIn('되돌아갔습니다', result['failed'][0]['why'])

    def test_a_screen_with_no_date_field_is_left_alone(self):
        page, _ = self.page(boxes=0)
        result = neis_actions.set_date(page, '2026.09.10.')
        self.assertEqual(result, {'set': [], 'failed': [], 'boxes': 0, 'locked': 0})
        page.keyboard.type.assert_not_called()

    def test_a_locked_period_is_not_clicked_at_all(self):
        """과목별출결현황의 `기간` 은 학기가 박혀 있어 누를 수 없다. 누르러 가면 칸마다
        8초씩 기다리다 실패한다 (2026-09-15 실측). 잠긴 것은 세기만 한다."""
        page, _ = self.page(boxes=0, locked=2)
        result = neis_actions.set_date(page, '2026.09.10.')
        self.assertEqual(result, {'set': [], 'failed': [], 'boxes': 0, 'locked': 2})
        page.locator.assert_not_called()
        page.keyboard.type.assert_not_called()

    def test_nothing_happens_without_a_date(self):
        page, _ = self.page()
        self.assertEqual(neis_actions.set_date(page, ''),
                         {'set': [], 'failed': [], 'boxes': 0, 'locked': 0})
        page.evaluate.assert_not_called()

    def test_every_date_box_gets_the_same_day(self):
        """`기간` 화면은 시작·종료 두 칸이다. "9월 10일" 은 그 하루를 뜻한다."""
        page, _ = self.page(boxes=2)
        with patch('core.neis_nav.wait_loading'):
            result = neis_actions.set_date(page, '2026.09.10.')
        self.assertEqual(len(result['set']), 2)
        self.assertEqual(page.keyboard.type.call_count, 2)

    def test_finish_sets_the_date_before_pressing_search(self):
        page, _ = self.page()
        order = []
        with patch('core.neis_actions.set_date',
                   side_effect=lambda *a, **k: order.append('date') or
                   {'set': [{'value': '2026.09.10.(목)'}], 'failed': [], 'boxes': 1}), \
             patch('core.neis_actions.search',
                   side_effect=lambda *a, **k: order.append('search') or True), \
             patch('core.neis_actions.pick_row',
                   return_value={'picked': None, 'matches': [], 'rows': []}), \
             patch('core.neis_nav.wait_overlay_gone'), patch('core.neis_nav.dismiss_dialogs',
                                                             return_value=0):
            done = neis_actions.finish(page, date='2026.09.10.')
        self.assertEqual(order, ['date', 'search'])
        self.assertEqual(done['dated']['set'][0]['value'], '2026.09.10.(목)')


class LoadingOverlayGateTests(unittest.TestCase):
    """로딩 덮개가 안 걷히면 밀고 나가지 않고 이유를 짚는다.

    2026-09-14 실측: 로컬 네트워크 권한이 막히면 덮개가 45초 내내 걷히지 않는다.
    예전 코드는 15초만 기다린 뒤 그냥 눌렀고, 그 클릭은 덮개에 먹혀 사라졌다.
    """

    def test_a_covered_screen_stops_with_the_reason(self):
        with patch('core.portal.wait_overlay_gone', return_value=False):
            with self.assertRaises(portal.LoginError) as caught:
                portal.require_ready(Mock(), 'NEIS')
        message = str(caught.exception)
        self.assertIn('로딩 표시가', message)
        self.assertIn('다른 앱 및 서비스에 액세스', message)      # 사용자가 보는 문구 그대로
        self.assertIn('LoopbackNetworkAllowedForUrls', message)   # 학교 배포용 해법

    def test_a_clear_screen_passes_quietly(self):
        with patch('core.portal.wait_overlay_gone', return_value=True):
            self.assertIsNone(portal.require_ready(Mock(), 'NEIS'))

    def test_the_widget_is_not_opened_while_the_screen_is_covered(self):
        """덮개 아래로 들어간 클릭은 조용히 사라진다. 누르기 전에 막아야 한다."""
        press = Mock(return_value=True)
        with patch('core.portal.wait_overlay_gone', return_value=False), \
             patch('core.portal.find_cert_root') as find:
            with self.assertRaises(portal.LoginError):
                portal.open_cert_widget(Mock(), 'NEIS', press)
        press.assert_not_called()
        find.assert_not_called()

    def test_one_missed_click_is_retried_before_giving_up(self):
        """덮개가 막 걷힌 직후에는 앱이 클릭을 못 받는 때가 있다."""
        press = Mock(return_value=True)
        root = object()
        with patch('core.portal.wait_overlay_gone', return_value=True), \
             patch('core.portal.find_cert_root', side_effect=[None, root]):
            got = portal.open_cert_widget(Mock(), 'NEIS', press)
        self.assertIs(got, root)
        self.assertEqual(press.call_count, 2)

    def test_it_gives_up_with_the_certificate_hint(self):
        press = Mock(return_value=True)
        with patch('core.portal.wait_overlay_gone', return_value=True), \
             patch('core.portal.find_cert_root', return_value=None):
            with self.assertRaises(portal.LoginError) as caught:
                portal.open_cert_widget(Mock(), 'NEIS', press)
        self.assertEqual(press.call_count, 2)
        self.assertIn('인증서 위젯이 뜨지 않았습니다', str(caught.exception))

    def test_a_button_that_is_not_there_is_reported_as_such(self):
        with patch('core.portal.wait_overlay_gone', return_value=True):
            with self.assertRaises(portal.LoginError) as caught:
                portal.open_cert_widget(Mock(), 'NEIS', lambda: False)
        self.assertIn('버튼을 찾지 못했습니다', str(caught.exception))

    def test_the_budget_is_long_enough_for_a_slow_machine(self):
        """권한이 허용돼 있으면 0.5초면 걷힌다. 넉넉히 잡아도 손해가 없다."""
        self.assertGreaterEqual(portal.OVERLAY_WAIT, 40)


class RiroLoginTests(unittest.TestCase):
    """리로스쿨은 인증서를 쓰지 않는다. 아이디·비밀번호뿐이라 흐름이 짧다."""

    def page(self, state=None, signed_in=True):
        page = Mock()
        page.evaluate.return_value = state or {'ok': True, 'user': '권민결', 'url': 'x'}
        if not signed_in:
            from playwright.sync_api import TimeoutError as PWTimeout
            page.wait_for_function.side_effect = [None, PWTimeout('시간 초과')]
        return page

    def test_a_missing_id_or_password_is_refused_before_the_browser_moves(self):
        for args in (('', 'pw'), ('me', '')):
            page = self.page()
            with self.assertRaises(portal.LoginError):
                portal.login_riro(page, *args)
            page.goto.assert_not_called()

    def test_it_fills_both_boxes_and_presses_login(self):
        page = self.page()
        # 들어가기 전에는 ok=False, 로그인 뒤에는 ok=True 로 보인다.
        page.evaluate.side_effect = [{'ok': False, 'user': None, 'url': 'x'},
                                     {'ok': True, 'user': '권민결', 'url': 'y'}]
        with patch('core.portal.require_ready'):
            answer = portal.login_riro(page, ' teacher ', 'secret')
        page.goto.assert_called_once()
        self.assertEqual(page.locator.call_args_list[0].args[0], portal.RIRO_ID)
        self.assertEqual(page.locator.call_args_list[1].args[0], portal.RIRO_PW)
        # 아이디의 앞뒤 공백은 지우고, 비밀번호는 그대로 넣는다.
        filled = [c.args[0] for c in page.locator.return_value.fill.call_args_list]
        self.assertEqual(filled, ['teacher', 'secret'])
        self.assertTrue(answer['ok'])

    def test_an_already_open_session_is_reused(self):
        page = self.page({'ok': True, 'user': '권민결', 'url': 'x'})
        with patch('core.portal.require_ready') as gate:
            portal.login_riro(page, 'teacher', 'secret')
        gate.assert_not_called()            # 이미 들어와 있으면 아무것도 누르지 않는다
        page.locator.assert_not_called()

    def test_a_wrong_password_is_reported_as_such(self):
        page = self.page({'ok': False, 'user': None, 'url': 'x'}, signed_in=False)
        page.evaluate.side_effect = [{'ok': False, 'user': None, 'url': 'x'},
                                     '비밀번호가 일치하지 않습니다']
        with patch('core.portal.require_ready'):
            with self.assertRaises(portal.LoginError) as caught:
                portal.login_riro(page, 'teacher', 'wrong')
        self.assertIn('아이디·비밀번호를 확인해 주세요', str(caught.exception))

    def test_riro_is_a_launchable_target_with_its_own_profile(self):
        with patch('core.portal.os.makedirs'), \
             patch('core.portal.os.path.join', side_effect=lambda *p: '/'.join(p)):
            playwright = Mock()
            portal.launch(playwright, target='riro')
        folder = playwright.chromium.launch_persistent_context.call_args.args[0]
        self.assertIn('browser-riro-msedge', folder)

    def test_the_signed_in_test_does_not_mistake_the_login_page(self):
        """로그인 전 화면에는 '로그인이 필요합니다' 가 있다. 그걸 성공으로 읽으면 안 된다."""
        self.assertIn('로그인이 필요합니다', portal.RIRO_SIGNED_IN)
        self.assertIn('로그아웃', portal.RIRO_SIGNED_IN)


class AiepLoginTests(unittest.TestCase):
    """전북 AIEP 도 아이디·비밀번호다. 다만 **들어가는 순서**를 지켜야 한다."""

    def page(self, states):
        page = Mock()
        page.evaluate.side_effect = list(states)
        return page

    def test_it_starts_at_the_home_page_not_the_form(self):
        """폼 주소로 바로 가면 제출 뒤 무한 리디렉션에 빠진다 (2026-09-14 실측)."""
        page = self.page([{'ok': False, 'user': None, 'url': 'x'},
                          {'ok': True, 'user': None, 'url': 'y'}])
        with patch('core.portal.aiep_open_form', return_value=True):
            portal.login_aiep(page, 'teacher', 'secret')
        self.assertEqual(page.goto.call_args.args[0], portal.AIEP_HOME)
        self.assertNotIn('mode=form', page.goto.call_args.args[0])

    def test_the_form_is_reached_by_choosing_the_role_then_the_user_login(self):
        page = Mock()
        page.locator.return_value.count.side_effect = [0, 1, 1]   # 링크 있음 → 암호칸 나옴
        with patch('core.portal.dom_click', return_value=True) as click, \
             patch('core.portal.aiep_pick_role', return_value='교원(교직원)') as role:
            self.assertTrue(portal.aiep_open_form(page))
        self.assertEqual([c.kwargs.get('text') for c in click.call_args_list], ['닫기'])   # 공지 닫고
        role.assert_called_once_with(page)                                               # 역할 고르기

    def test_the_role_button_is_looked_up_by_its_current_and_old_labels(self):
        """2026-10 에 '교사' 단추가 '교원(교직원)' 으로 바뀌어 자동 로그인이 멈췄다 (사용자 보고)."""
        self.assertEqual(portal.AIEP_ROLES[:2], ('교원(교직원)', '교원'))
        self.assertIn('교사', portal.AIEP_ROLES)
        page = Mock()
        page.evaluate.return_value = '교원(교직원)'
        self.assertEqual(portal.aiep_pick_role(page), '교원(교직원)')
        self.assertEqual(page.evaluate.call_args.args[1], list(portal.AIEP_ROLES))

    def test_a_missing_role_button_is_reported(self):
        page = Mock()
        with patch('core.portal.dom_click', return_value=False), \
             patch('core.portal.aiep_pick_role', return_value=None):
            with self.assertRaises(portal.LoginError) as caught:
                portal.aiep_open_form(page)
        self.assertIn('교사', str(caught.exception))

    def test_the_mail_suffix_is_trimmed_from_the_id(self):
        """화면의 아이디 칸은 @ai.jbedu.kr 앞부분만 받는다."""
        page = self.page([{'ok': False, 'user': None, 'url': 'x'},
                          {'ok': True, 'user': None, 'url': 'y'}])
        with patch('core.portal.aiep_open_form', return_value=True):
            portal.login_aiep(page, 'teacher@ai.jbedu.kr', 'secret')
        # `fill` 로는 로그인이 붙지 않는다. 사람처럼 한 글자씩 쳐야 숨은 email 칸이 찬다.
        typed = [c.args[0] for c in
                 page.locator.return_value.first.press_sequentially.call_args_list]
        self.assertEqual(typed, ['teacher', 'secret'])

    def test_a_missing_id_or_password_is_refused_before_the_browser_moves(self):
        for args in (('', 'pw'), ('me', '')):
            page = Mock()
            with self.assertRaises(portal.LoginError):
                portal.login_aiep(page, *args)
            page.goto.assert_not_called()

    def test_an_already_open_session_is_reused(self):
        page = self.page([{'ok': True, 'user': '권민결', 'url': 'x'}])
        with patch('core.portal.aiep_open_form') as form:
            answer = portal.login_aiep(page, 'teacher', 'secret')
        self.assertTrue(answer['ok'])
        form.assert_not_called()

    def test_a_form_that_never_appears_is_reported(self):
        page = self.page([{'ok': False, 'user': None, 'url': 'x'}])
        with patch('core.portal.aiep_open_form', return_value=False):
            with self.assertRaises(portal.LoginError) as caught:
                portal.login_aiep(page, 'teacher', 'secret')
        self.assertIn('로그인 폼이 뜨지 않았습니다', str(caught.exception))

    def test_a_login_that_does_not_take_says_what_to_check(self):
        from playwright.sync_api import TimeoutError as PWTimeout
        page = Mock()
        page.evaluate.return_value = {'ok': False, 'user': None, 'url': 'x'}
        page.wait_for_function.side_effect = PWTimeout('시간 초과')
        with patch('core.portal.aiep_open_form', return_value=True):
            with self.assertRaises(portal.LoginError) as caught:
                portal.login_aiep(page, 'teacher', 'wrong')
        message = str(caught.exception)
        self.assertIn('아이디·비밀번호를 확인해 주세요', message)
        self.assertIn('정부 통합로그인', message)      # 다른 길을 쓰는 분도 있다

    def test_coming_back_to_the_landing_page_is_not_success(self):
        """로그인이 안 돼도 첫 화면으로 되돌아온다. 그걸 성공으로 읽으면 안 된다."""
        self.assertIn('회원가입', portal.AIEP_SIGNED_IN)
        self.assertIn('아이디 찾기', portal.AIEP_SIGNED_IN)

    def test_aiep_is_a_launchable_target_with_its_own_profile(self):
        with patch('core.portal.os.makedirs'),              patch('core.portal.os.path.join', side_effect=lambda *p: '/'.join(p)):
            playwright = Mock()
            portal.launch(playwright, target='aiep')
        self.assertIn('browser-aiep-msedge',
                      playwright.chromium.launch_persistent_context.call_args.args[0])

    def test_being_signed_in_is_judged_by_where_we_are_not_by_wording(self):
        """끝난 화면의 문구는 개편마다 바뀐다. 인증 서버를 벗어났는지로 본다."""
        self.assertIn('#password', portal.AIEP_SIGNED_IN)
        self.assertIn('ai-auth', portal.AIEP_SIGNED_IN)
        self.assertIn('jbedu.kr', portal.AIEP_SIGNED_IN)


class BrowserFeelsLikeMineTests(unittest.TestCase):
    """자동 로그인 창에서 Edge 에 로그인하면 평소 환경이 따라와야 한다 (2026-09-15 요청)."""

    def launched(self, **extra):
        with patch('core.portal.os.makedirs'), \
             patch('core.portal.os.path.join', side_effect=lambda *p: '/'.join(p)):
            playwright = Mock()
            portal.launch(playwright, **extra)
        return playwright.chromium.launch_persistent_context.call_args

    def test_sync_and_extensions_are_not_switched_off(self):
        """이 둘을 꺼 두면 로그인해도 즐겨찾기·설정이 하나도 넘어오지 않는다."""
        ignored = self.launched().kwargs['ignore_default_args']
        self.assertIn('--disable-sync', ignored)
        self.assertIn('--disable-extensions', ignored)

    def test_the_first_run_screen_stays_suppressed(self):
        """`--no-first-run` 을 풀면 안내 화면이 떠서 자동화를 막는다."""
        self.assertNotIn('--no-first-run', self.launched().kwargs['ignore_default_args'])

    def test_the_window_is_still_maximised_and_unframed(self):
        call = self.launched()
        self.assertIn('--start-maximized', call.kwargs['args'])
        self.assertTrue(call.kwargs['no_viewport'])

    def test_it_still_uses_our_own_profile_not_the_everyday_one(self):
        """평소 프로필을 쓰면 Edge 가 이미 켜져 있을 때 제어를 잃는다."""
        folder = self.launched(target='neis').args[0]
        self.assertIn('SpacekijunDesk', folder)
        self.assertNotIn('Microsoft', folder)
