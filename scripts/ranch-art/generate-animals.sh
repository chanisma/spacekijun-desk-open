#!/usr/bin/env bash
# 별사이 목장 동물 2판 (2026-11-06) — 다마고찌 화풍이 아니라 더 세밀한 픽셀 아트, 옆모습, 어른·아기를 따로.
# 어른(a_<종>)을 먼저 그리고, 아기(b_<종>)는 그 어른 그림을 참조로 붙여 «같은 동물의 아기»로 그린다.
# 결과 = .tmp_ranch/a_<종>-raw.png · b_<종>-raw.png (있으면 건너뛴다). 스프라이트로 = build.py
#   bash scripts/ranch-art/generate-animals.sh rabbit fox ...   (이름 없이 부르면 여덟 종 전부)
set -u
cd "$(dirname "$0")/../.."
OUT=.tmp_ranch
mkdir -p "$OUT"
STYLE_REF="$OUT/bg_meadow-raw.png"          # 배경과 같은 파스텔 색감

STYLE='Style: polished, high-detail modern pixel art for a cozy indie farming game (finer than a Tamagotchi): every game pixel is a square block of exactly 3x3 image pixels, crisp edges, no anti-aliasing, no blur. Soft pastel palette that matches the attached pastel landscape, 4-6 shading tones per color, gentle highlights, a clean 1-game-pixel outline in a dark warm color (not pure black). Natural but cute proportions.
Layout: landscape 1536x1024. FIVE sprites in ONE horizontal row, each centered in an equal-width column, all standing on the same baseline, every sprite in SIDE VIEW facing RIGHT. Solid flat pure magenta #FF00FF background everywhere. No floor, no shadow, no text, no labels, no borders.
Poses, left to right:
1) idle — standing calmly
2) happy — a small hop with a happy face
3) eating — head lowered to the ground, nibbling
4) sleeping — lying down, eyes closed
5) sulking — sitting slumped, droopy ears or head, sad face (not angry)
Same exact animal design, colors and proportions in all five poses.'

describe() {   # 종 → 어른 모습
  case "$1" in
    rabbit)   echo 'a white RABBIT with long upright ears with soft pink insides, a pink nose, a fluffy round tail' ;;
    chick)    echo 'a plump HEN (adult chicken): warm cream-white feathers with light brown tips, a small red comb and wattle, an orange beak and orange legs' ;;
    duckling) echo 'a white farm DUCK with an orange bill and orange webbed feet, a slightly curled tail feather' ;;
    lamb)     echo 'a fluffy SHEEP with thick curly cream-white wool, a soft grey face and grey legs, small ears' ;;
    kitten)   echo 'a ginger-and-white tabby CAT with darker orange stripes, white chest and paws, a long striped tail held up' ;;
    puppy)    echo 'a tan-and-cream SHIBA dog with small pointed ears, a cream muzzle and chest, a curled tail on its back' ;;
    fox)      echo 'an orange red FOX with a cream face and chest, black-tipped ears and legs, a big fluffy tail with a white tip' ;;
    alpaca)   echo 'a fluffy cream ALPACA with a long woolly neck, a fluffy cloud-like head tuft, banana-shaped ears and a gentle face' ;;
  esac
}

ALL='rabbit chick duckling lamb kitten puppy fox alpaca'
for sp in ${@:-$ALL}; do
  for stage in a b; do
    name="${stage}_${sp}"
    target="$OUT/$name-raw.png"
    [ -f "$target" ] && { echo "skip $target"; continue; }
    prompt="$OUT/prompt-$name.txt"
    refs=(-i "$STYLE_REF")
    {
      echo 'Use the image generation tool to create ONE image. Do not write code.'
      echo
      echo 'MOST IMPORTANT: the background must be ONE flat solid color, pure magenta #FF00FF, filling the whole image edge to edge. NOT black, NOT dark, NO glow, NO halo, NO vignette, NO shadows.'
      echo
      if [ "$stage" = a ]; then
        echo "Draw ONE grown-up animal: $(describe "$sp"). Each sprite about 80 game pixels tall."
      else
        if [ "$sp" = chick ]; then        # 병아리는 어미와 색이 다르다 — 노란 솜털(2026-11-06, 작은 암탉처럼 나와 다시 그림)
          echo "Draw the BABY of the attached hen (the second attached image shows the grown-up): a tiny round fluffy YELLOW CHICK covered in soft yellow down, NO comb, NO wattle, a small orange beak, tiny orange legs, big shiny eyes. Each sprite about 50 game pixels tall."
        else
          echo "Draw the BABY of the attached animal (the second attached image shows the grown-up): the same species, the same colors and markings, but clearly a young baby — a bigger head, rounder softer body, shorter legs, bigger eyes, fluffier. Each sprite about 60 game pixels tall."
        fi
        refs+=(-i "$OUT/a_${sp}-raw.png")
      fi
      echo 'The attached landscape is only a palette and style reference — do not draw it.'
      echo
      echo "$STYLE"
    } > "$prompt"
    if [ "$stage" = b ] && [ ! -f "$OUT/a_${sp}-raw.png" ]; then echo "FAILED $name (어른이 없다)"; continue; fi
    stamp="$OUT/.stamp-$name"; touch "$stamp"
    codex exec --skip-git-repo-check "${refs[@]}" < "$prompt" > "$OUT/$name.log" 2>&1
    made=$(find "$CODEX_HOME/generated_images" -newer "$stamp" -name '*.png' 2>/dev/null | head -1)
    if [ -n "$made" ]; then cp "$made" "$target"; echo "made $target"; else echo "FAILED $name (see $OUT/$name.log)"; fi
  done
done
