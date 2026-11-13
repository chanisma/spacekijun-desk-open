/**
 * 설정·경로 한곳에서 정하기.
 *   데이터 폴더(EDUFINE_HOME): 환경변수 EDUFINE_HOME 또는 %USERPROFILE%\.edufine
 *     config.json        { baseUrl, cdpPort, browserChannel, wxsClient }
 *     credentials.json   { id, certPassword, certMatch? }   ← 사용자가 직접 작성(채팅에 붙여 넣지 않는다)
 *     ledger/            문서등록대장 CSV 캐시
 *     docs/              내려받은 공문
 *     logs/기안로그/      기안 기록
 *     browser-profile/   인증서 권한 승인이 남는 고정 브라우저 프로필
 */
const fs = require('fs');
const os = require('os');
const path = require('path');

const HOME = process.env.EDUFINE_HOME || path.join(os.homedir(), '.edufine');
const DEFAULTS = { baseUrl: 'https://klef.jbe.go.kr', cdpPort: 9344, browserChannel: null, wxsClient: 'C:/Program Files (x86)/kedu/WXSClient.exe' };

function readJson(f, fallback) {
  try { return JSON.parse(fs.readFileSync(f, 'utf8').replace(/^﻿/, '')); } catch (e) { return fallback; }
}

const config = Object.assign({}, DEFAULTS, readJson(path.join(HOME, 'config.json'), {}));
config.baseUrl = String(config.baseUrl).replace(/\/+$/, '');
if (process.env.EDUFINE_CDP_PORT) config.cdpPort = Number(process.env.EDUFINE_CDP_PORT);

const paths = {
  home: HOME,
  config: path.join(HOME, 'config.json'),
  credentials: path.join(HOME, 'credentials.json'),
  ledger: path.join(HOME, 'ledger'),
  docs: path.join(HOME, 'docs'),
  logs: path.join(HOME, 'logs'),
  profile: path.join(HOME, 'browser-profile'),
  sessionMark: path.join(HOME, '.session.json'),
};

/**
 * 스페이스기전 데스크(교사판)에 저장된 인증서 계정 — credentials.json 이 없을 때만 읽는다.
 * Windows DPAPI 로 이 PC 의 이 사용자만 풀 수 있다. 업무포털 아이디·인증서 암호·인증서 이름 셋만 꺼내고 나머지는 쓰지 않는다.
 * 암호는 자식 프로세스 출력으로만 오가고 화면·로그에 남지 않는다.
 */
function deskCredentials() {
  const store = path.join(process.env.LOCALAPPDATA || '', 'SpacekijunDesk', 'credentials.dat');
  if (!process.env.LOCALAPPDATA || !fs.existsSync(store)) return null;
  const script = "[Console]::OutputEncoding=[Text.Encoding]::UTF8; Add-Type -AssemblyName System.Security; "
    + "$p=[Security.Cryptography.ProtectedData]::Unprotect([IO.File]::ReadAllBytes($env:EDUFINE_DESK_STORE),$null,'CurrentUser'); "
    + "$v=[Text.Encoding]::UTF8.GetString($p)|ConvertFrom-Json; "
    + "@{id=$v.id;certPassword=$v.cert_password;certMatch=$v.cert_match}|ConvertTo-Json -Compress";
  const r = require('child_process').spawnSync('powershell.exe', ['-NoProfile', '-NonInteractive', '-Command', script],
    { env: Object.assign({}, process.env, { EDUFINE_DESK_STORE: store }), encoding: 'utf8', timeout: 20000, windowsHide: true });
  try {
    const c = JSON.parse(String(r.stdout || '').trim());
    return c && c.id && c.certPassword ? c : null;
  } catch (e) { return null; }
}

function credentials() {
  const c = readJson(paths.credentials, null);
  if (c && c.id && c.certPassword && !/여기에/.test(c.id + c.certPassword)) return c;
  const desk = deskCredentials();
  if (desk) return desk;
  throw new Error(`자격증명이 없습니다. ${paths.credentials} 에 {"id":"업무포털 아이디","certPassword":"인증서 암호"} 를 직접 적어 주세요 (node edufine.js setup 으로 틀을 만들 수 있음). 스페이스기전 데스크를 쓰면 데스크 설정에 저장한 인증서 정보를 그대로 씁니다.`);
}

/** 처음 쓸 때 폴더와 설정 틀을 만든다 (있는 파일은 건드리지 않는다) */
function setup() {
  for (const d of [HOME, paths.ledger, paths.docs, paths.logs]) fs.mkdirSync(d, { recursive: true });
  const made = [];
  if (!fs.existsSync(paths.config)) { fs.writeFileSync(paths.config, JSON.stringify(DEFAULTS, null, 2)); made.push(paths.config); }
  if (!fs.existsSync(paths.credentials)) {
    fs.writeFileSync(paths.credentials, JSON.stringify({ id: '여기에 업무포털 아이디', certPassword: '여기에 인증서 암호', certMatch: '' }, null, 2));
    made.push(paths.credentials);
  }
  return { home: HOME, made };
}

const host = () => new URL(config.baseUrl).host;
module.exports = { config, paths, credentials, setup, host };
