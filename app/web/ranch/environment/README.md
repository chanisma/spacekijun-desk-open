# 오리지널 시설 · 풍경

내장 imagegen으로 생성한 새 원화와 게임용 시트. 원본 TinyPasture는 동작 구성과
투명 배경 층의 참고 자료로 사용했다.

- `*-source.png`: 원화 8장. 시설 4열×2행, 풍경 3개 가로 층.
- `broom/feeder/jar/curtain.webp`: 시설별 8프레임, 112×112 셀.
- `bg-*.webp`: 풍경별 3개 층, 각 1536×104.
- `atlas.js`: 파일·프레임·발밑 기준·배경 윤곽·구 ID 호환.
- `manifest.json`: 원화 해시와 프레임/층 위치.

컴파일: `python scripts/ranch-art/build-environment.py`

[미리보기](../../ranch-environment.html) · [제작 기록 및 프롬프트](../../../../docs/ranch-art/ENVIRONMENT.md)
