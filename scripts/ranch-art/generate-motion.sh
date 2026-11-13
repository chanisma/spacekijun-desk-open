#!/usr/bin/env bash
# 별사이 목장 동작 그림 (2026-11-07) — 걷기 6프레임(어른·아기)과 머리 위 말풍선 아이콘.
# 프레임 수·동작 구성은 참고 게임(Tiny Pasture)의 «수치»만 따른다(그 게임의 그림은 생성기에 넣지 않는다 — 저작권).
# 생김새는 우리 원화(.tmp_ranch/a_<종>-raw.png · b_<종>-raw.png)를 참조로 붙여 같은 동물로.
#   bash scripts/ranch-art/generate-motion.sh rabbit fox ... bubbles   (이름 없이 부르면 전부)
set -u
cd "$(dirname "$0")/../.."
OUT=.tmp_ranch
mkdir -p "$OUT"

STYLE='Style: exactly the same polished high-detail pixel art as the attached sprite sheet (same outline color, same shading, same palette, same proportions, same size). Every game pixel is a square block of exactly 3x3 image pixels, crisp edges, no anti-aliasing.
Layout: landscape 1536x1024. SIX frames in ONE horizontal row, each centered in an equal-width column, all standing on the same baseline, SIDE VIEW facing RIGHT. Solid flat pure magenta #FF00FF background everywhere. No floor, no shadow, no text, no labels, no borders.'

ALL='rabbit chick duckling lamb kitten puppy fox alpaca bubbles'
for item in ${@:-$ALL}; do
  if [ "$item" = bubbles ]; then jobs="bubbles"; else jobs="wa_$item wb_$item"; fi
  for name in $jobs; do
    target="$OUT/$name-raw.png"
    [ -f "$target" ] && { echo "skip $target"; continue; }
    prompt="$OUT/prompt-$name.txt"
    refs=()
    {
      echo 'Use the image generation tool to create ONE image. Do not write code.'
      echo
      echo 'MOST IMPORTANT: the background must be ONE flat solid color, pure magenta #FF00FF, filling the whole image edge to edge. NOT black, NOT dark, NO glow, NO shadows.'
      echo
      case "$name" in
        bubbles)
          refs=(-i "$OUT/a_rabbit-raw.png")
          echo 'Draw ONLY small speech-bubble status icons for a cozy pixel-art farm game (same pixel style as the attached sheet). Each is a small rounded white speech bubble with a dark warm outline and a tiny tail at the bottom, about 18 game pixels wide, with ONE symbol inside. NO characters, NO text letters.'
          echo 'Exactly 8 icons in ONE horizontal row, left to right:'
          echo '1) a small pink heart (happy)  2) a brown smudge with flies lines (dirty)  3) a carrot with a tiny magnifier (looking for food)  4) a stack of three violet crystal shards (storage full)'
          echo '5) two small pink hearts (love)  6) a green leaf with a tiny plus (healthy again)  7) an empty food bowl (hungry)  8) a pale blue thermometer with a sweat drop (sick)'
          echo 'Each bubble centered in an equal-width column, solid flat magenta #FF00FF background everywhere, no text.'
          ;;
        wa_*|wb_*)
          sp=${name#w?_}; stage=${name:1:1}
          refs=(-i "$OUT/${stage}_${sp}-raw.png")
          echo "Draw a smooth 6-frame WALK CYCLE of the attached animal (the attached sheet shows it — use its FIRST pose as the design). Legs alternate naturally, the body bobs gently up and down, the head stays level; frame 6 loops back to frame 1."
          echo
          echo "$STYLE"
          ;;
      esac
    } > "$prompt"
    stamp="$OUT/.stamp-$name"; touch "$stamp"
    codex exec --skip-git-repo-check "${refs[@]}" < "$prompt" > "$OUT/$name.log" 2>&1
    made=$(find "$CODEX_HOME/generated_images" -newer "$stamp" -name '*.png' 2>/dev/null | head -1)
    if [ -n "$made" ]; then cp "$made" "$target"; echo "made $target"; else echo "FAILED $name (see $OUT/$name.log)"; fi
  done
done
