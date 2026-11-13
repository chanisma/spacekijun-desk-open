# SPACEKIJUN 데스크 · 학생판 · 교실 — 공개판

[SPACEKIJUN 웹](https://github.com/chanisma/spacekijun-open)과 짝을 이루는 Windows·안드로이드 앱 모음입니다.
실제 학교 데이터는 들어 있지 않습니다(사람 이름·이메일·학번은 가상 값, 키·조직 ID 는 자리표시값).

| 앱 | 진입점 | 빌드 명세 |
|---|---|---|
| 데스크(교사판) | `app/desktop.py` | `SpacekijunDesk.spec` |
| 학생판(독) | `app/student.py` | `SpacekijunStudent.spec` |
| 교실 기기 | `app/classroom.py` (`app/CLASSROOM.md`) | `SpacekijunClassroom.spec` |
| NEIS 도우미 | `app/main.py` | `SpacekijunNeis.spec` |
| 교실 안드로이드 | `android/` | `deploy/classroom-android/build.py` |

## 설정

- Supabase 주소·키: `app/resources/public-config.json` 의 `your-project-ref` · `YOUR_SUPABASE_ANON_KEY` 를 내 프로젝트 값으로
  (안드로이드는 `android/app/src/main/java/.../Link.kt`)
- 학교 메일 도메인 `myschool.hs.kr`, 학교 이름 `샘플고` 는 검색·치환으로 바꿉니다
- 계정 비밀번호·인증서 암호는 저장소가 아니라 각 PC 의 Windows DPAPI 저장소에 들어갑니다(`app/core/secretstore.py`)
- Intune 배포 스크립트(`deploy/intune*`)의 테넌트·앱 ID 는 0 으로 비워 두었습니다 — 환경변수로 넣습니다

## 개발

```bash
pip install -r app/requirements.txt
python app/desktop.py
pyinstaller SpacekijunDesk.spec
```

나이스·에듀파인·리로스쿨 등 외부 시스템 자동화는 각 기관의 이용 약관과 학교 정책을 확인한 뒤 사용하세요.

## 라이선스

[SPACEKIJUN 교육용 비상업 라이선스 1.0](LICENSE)

- **학교 안 활용은 자유롭습니다.** 학교(국공립·사립)와 교직원·학생이 수업·학교 업무·학생 활동에 쓰고, 자기 학교에 맞게 고치고, 학교 서버나 교육청 클라우드에 설치해 운영할 수 있습니다. 교육청·교사 연구회·비영리 교육 단체가 고친 것을 다른 학교와 나누는 것도 자유입니다.
- **상용 서비스 제작에는 쓸 수 없습니다.** 유료 판매·구독 상품, 영리 목적의 웹 서비스·앱(수익 방식 불문), 영리 기업 제품이나 사교육 상품에 넣는 것은 저작권자의 서면 허락이 필요합니다.
- 외부에서 가져온 코드·자료는 각자의 라이선스를 따릅니다.
