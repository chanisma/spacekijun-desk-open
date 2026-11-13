#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
생활기록부 바이트 카운터 (NEIS 단순 모델).

분량 규칙(사용자 지정 기본값):
  - 한글(완성형 가-힣 + 자모)        : 3바이트
  - 엔터(줄바꿈)                     : 2바이트
  - 그 외 모든 문자(영어/숫자/특수문자/공백): 1바이트

이 모델은 순수 UTF-8 바이트 길이와 다르다. 학교/NEIS에서 통용되는
'한글 3 / 엔터 2 / 나머지 1' 단순 규칙을 그대로 구현한 것이다.
다른 과목/지역에서 규칙이 다르면 is_hangul() 범위나 가중치만 바꾸면 된다.

사용법
  단일 문자열   : python byte_count.py "평가문 텍스트"
  파일          : python byte_count.py --file 평가문.txt
  통합 JSON 검수: python byte_count.py --json students.json --write
                  (각 학생 평가문의 바이트수를 계산해 '바이트수' 필드에 기록하고,
                   '목표바이트' 범위와 비교한 합격/초과 표를 출력)
"""
import sys
import json
import re
import argparse

# Windows 콘솔 한글 출력 보호
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass


def is_hangul(ch: str) -> bool:
    o = ord(ch)
    return (
        0xAC00 <= o <= 0xD7A3  # 완성형 음절
        or 0x1100 <= o <= 0x11FF  # 자모
        or 0x3130 <= o <= 0x318F  # 호환 자모
        or 0xA960 <= o <= 0xA97F  # 확장 자모-A
        or 0xD7B0 <= o <= 0xD7FF  # 확장 자모-B
    )


def count_bytes(text: str) -> int:
    """사용자 지정 규칙으로 바이트 수 계산."""
    if not text:
        return 0
    # 줄바꿈 정규화: \r\n, \r -> \n  (엔터 1회 = 2바이트)
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    total = 0
    for ch in text:
        if ch == "\n":
            total += 2
        elif is_hangul(ch):
            total += 3
        else:
            total += 1
    return total


def parse_target(spec) -> tuple:
    """'1400~1500' / '1400-1500' / '~1500' / '1500' -> (min, max)."""
    if spec is None:
        return (None, None)
    nums = re.findall(r"\d+", str(spec))
    if len(nums) >= 2:
        return (int(nums[0]), int(nums[1]))
    if len(nums) == 1:
        # 단일 숫자는 상한으로 해석
        return (None, int(nums[0]))
    return (None, None)


def verdict(n: int, target) -> str:
    lo, hi = parse_target(target)
    if hi is not None and n > hi:
        return f"초과(+{n - hi})"
    if lo is not None and n < lo:
        return f"미달(-{lo - n})"
    if lo is None and hi is None:
        return "—"
    return "적정"


def main():
    p = argparse.ArgumentParser(description="생활기록부 바이트 카운터")
    p.add_argument("text", nargs="?", help="바이트를 셀 문자열")
    p.add_argument("--file", help="텍스트 파일 경로(UTF-8)")
    p.add_argument("--json", help="students.json 경로")
    p.add_argument("--field", default="평가문", help="평가문이 담긴 필드명")
    p.add_argument("--write", action="store_true", help="--json에 바이트수를 기록")
    args = p.parse_args()

    if args.json:
        with open(args.json, encoding="utf-8") as f:
            data = json.load(f)
        students = data.get("students", data if isinstance(data, list) else [])
        print(f"{'번호':<8}{'이름':<8}{'바이트':>7}  {'목표':<12}판정")
        print("-" * 48)
        for s in students:
            text = s.get(args.field, "") or ""
            n = count_bytes(text)
            s["바이트수"] = n
            tgt = s.get("목표바이트", "")
            print(f"{str(s.get('번호','')):<8}{str(s.get('이름','')):<8}{n:>7}  {str(tgt):<12}{verdict(n, tgt)}")
        if args.write:
            with open(args.json, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            print(f"\n→ 바이트수 기록 완료: {args.json}")
        return

    if args.file:
        with open(args.file, encoding="utf-8") as f:
            text = f.read()
    elif args.text is not None:
        text = args.text
    else:
        text = sys.stdin.read()
    print(count_bytes(text))


if __name__ == "__main__":
    main()
