/**
 * 설정·경로.
 *   데이터 폴더(NEIS_HOME): 환경변수 NEIS_HOME 또는 %USERPROFILE%\.neis
 *     config.json        { baseUrl, cdpPort, browserChannel }
 *     credentials.json   { certPassword, certMatch? }   ← 사용자가 직접 작성(채팅에 붙여 넣지 않는다)
 *     out/               내려받은 파일·수집 결과 (학생 개인정보 — 쓰고 나면 지운다)
 *     browser-profile/   인증서 권한 승인이 남는 고정 브라우저 프로필
 */
const fs = require('fs');
const os = require('os');
const path = require('path');

const HOME = process.env.NEIS_HOME || path.join(os.homedir(), '.neis');
const DEFAULTS = { baseUrl: 'https://jbe.neis.go.kr', cdpPort: 9336, browserChannel: null };
const readJson = (f, fb) => { try { return JSON.parse(fs.readFileSync(f, 'utf8').replace(/^﻿/, '')); } catch (e) { return fb; } };

const config = Object.assign({}, DEFAULTS, readJson(path.join(HOME, 'config.json'), {}));
config.baseUrl = String(config.baseUrl).replace(/\/+$/, '');
if (process.env.NEIS_CDP_PORT) config.cdpPort = Number(process.env.NEIS_CDP_PORT);

const paths = {
  home: HOME,
  config: path.join(HOME, 'config.json'),
  credentials: path.join(HOME, 'credentials.json'),
  out: path.join(HOME, 'out'),
  profile: path.join(HOME, 'browser-profile'),
  sessionMark: path.join(HOME, '.session.json'),
  knowledge: path.join(__dirname, '..', '..', 'knowledge'),
};

/**
 * 스페이스기전 데스크(교사판)에 저장된 인증서 정보 — credentials.json 이 없을 때만 읽는다 (edufine 스킬과 같은 방식).
 * Windows DPAPI 로 이 PC 의 이 사용자만 풀 수 있다. 인증서 암호·인증서 이름만 꺼내고 나머지는 쓰지 않는다.
 * 암호는 자식 프로세스 출력으로만 오가고 화면·로그에 남지 않는다.
 */
function deskCredentials() {
  const store = path.join(process.env.LOCALAPPDATA || '', 'SpacekijunDesk', 'credentials.dat');
  if (!process.env.LOCALAPPDATA || !fs.existsSync(store)) return null;
  const script = "[Console]::OutputEncoding=[Text.Encoding]::UTF8; Add-Type -AssemblyName System.Security; "
    + "$p=[Security.Cryptography.ProtectedData]::Unprotect([IO.File]::ReadAllBytes($env:NEIS_DESK_STORE),$null,'CurrentUser'); "
    + "$v=[Text.Encoding]::UTF8.GetString($p)|ConvertFrom-Json; "
    + "@{certPassword=$v.cert_password;certMatch=$v.cert_match}|ConvertTo-Json -Compress";
  const r = require('child_process').spawnSync('powershell.exe', ['-NoProfile', '-NonInteractive', '-Command', script],
    { env: Object.assign({}, process.env, { NEIS_DESK_STORE: store }), encoding: 'utf8', timeout: 20000, windowsHide: true });
  try {
    const c = JSON.parse(String(r.stdout || '').trim());
    return c && c.certPassword ? { certPassword: c.certPassword, certMatch: c.certMatch || '' } : null;
  } catch (e) { return null; }
}

function credentials() {
  const c = readJson(paths.credentials, null);
  if (c && c.certPassword && !/여기에/.test(c.certPassword)) return c;
  const desk = deskCredentials();
  if (desk) return desk;
  throw new Error(`자격증명이 없습니다. ${paths.credentials} 에 {"certPassword":"인증서 암호"} 를 직접 적어 주세요 (node neis.js setup 으로 틀을 만들 수 있음). 스페이스기전 데스크를 쓰면 데스크 설정에 저장한 인증서 정보를 그대로 씁니다.`);
}

/** 폴더·설정 틀 만들기. edufine 스킬을 이미 쓰고 있으면 인증서 암호를 거기서 가져올 수 있다(--from-edufine). */
function setup({ fromEdufine = false } = {}) {
  for (const d of [HOME, paths.out]) fs.mkdirSync(d, { recursive: true });
  const made = [];
  if (!fs.existsSync(paths.config)) { fs.writeFileSync(paths.config, JSON.stringify(DEFAULTS, null, 2)); made.push(paths.config); }
  if (!fs.existsSync(paths.credentials)) {
    let c = { certPassword: '여기에 인증서 암호', certMatch: '' };
    if (fromEdufine) {
      const e = readJson(path.join(process.env.EDUFINE_HOME || path.join(os.homedir(), '.edufine'), 'credentials.json'), null);
      if (e && e.certPassword && !/여기에/.test(e.certPassword)) c = { certPassword: e.certPassword, certMatch: e.certMatch || '' };
    }
    fs.writeFileSync(paths.credentials, JSON.stringify(c, null, 2)); made.push(paths.credentials);
  }
  return { home: HOME, made };
}

const host = () => new URL(config.baseUrl).host;
module.exports = { config, paths, credentials, setup, host };
