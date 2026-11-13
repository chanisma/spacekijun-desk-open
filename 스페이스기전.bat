@echo off
chcp 65001 > nul
rem 스페이스기전 웹앱을 기본 브라우저로 연다.
rem Playwright 를 쓰지 않는다 — 자동 조작이 필요 없고, 사용자의 평소 브라우저에서
rem 이미 로그인된 세션을 그대로 쓰는 편이 빠르다.
start "" "https://spacekijun.lovable.app"
