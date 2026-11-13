#!/usr/bin/env bash
# 별사이 목장(학생판) 그림 — codex 내장 image_generation 으로 원화를 그린다 (2026-11-06).
# 다마고찌(spacekijun scripts/tamagotchi-codex/generate.sh)와 같은 화풍·같은 참조 시트·같은 자세 다섯 —
# 목장 동물이 다마고찌 캐릭터와 한 세계로 보이게. 스프라이트로 바꾸기 = build.py (다마고찌 process.py 를 쓴다).
# 결과 = .tmp_ranch/<이름>-raw.png (이미 있으면 건너뛴다 — 다시 그리려면 지운다).
#   bash scripts/ranch-art/generate.sh rabbit chick ...      (이름 없이 부르면 전부)
set -u
cd "$(dirname "$0")/../.."
SPACEKIJUN=${SPACEKIJUN_REPO:-../spacekijun}
REF="$SPACEKIJUN/.tmp/tama-codex/reference-sheet.png"
OUT=.tmp_ranch
mkdir -p "$OUT"
[ -f "$REF" ] || (cd "$SPACEKIJUN" && npx tsx scripts/tamagotchi-test/color-sheet.mts .tmp/tama-codex/reference-sheet.png)

COMMON='Style: polished pixel art like a modern color Tamagotchi (Tamagotchi Uni / Pix) sprite. Every game pixel is drawn as a perfect square block of exactly 8x8 image pixels (no anti-aliasing, no blur, no gradients inside a block, no sub-block details). A dark purple 1-pixel outline, 3-4 tone cel shading with a small highlight, big glossy eyes with a white catchlight, pink blush. Cute, round, consistent proportions.
Layout: landscape 1536x1024. Sprites in ONE horizontal row, each centered in an equal-width column, all standing on the same baseline. Solid flat pure magenta #FF00FF background everywhere. No floor, no shadow, no text, no labels, no borders, no grid lines.'

POSES='Poses, left to right:
1) idle — standing, facing forward, calm smile
2) happy — jumping a little, eyes closed as ^ ^, open smile
3) eating — mouth wide open (dark mouth with pink tongue)
4) sleeping — lying down flat and wide, eyes closed as gentle curves
5) sulking — sitting a little slumped, droopy eyes looking down, small frown (sad, not angry)
Same exact character design, colors and proportions in all five poses.'

BGHEAD='Draw ONE image: a pixel-art SIDE-VIEW BACKGROUND for a tiny desktop farm game that sits at the bottom of a computer screen. NOT characters — no animals, no people, no text.
Layout: THREE separate horizontal panels stacked vertically, separated by flat magenta gaps. Each panel spans the FULL WIDTH of the image edge to edge and is about 280 image pixels tall. Each panel is one parallax layer drawn on pure flat magenta #FF00FF: everything that is not part of the layer (all sky, all empty space) must be flat magenta so the layer can be cut out. Keep the top of each panel empty (magenta) and draw the scenery rising from its bottom edge.
The left and right edges of every panel should match so it can tile.
Style: soft pastel pixel art matching the attached reference sheet. Every game pixel is a square block of exactly 6x6 image pixels, no anti-aliasing, no gradients, small palette.'

ANIMAL='Draw ONE cute round chibi BABY ANIMAL (a real animal, not a fantasy creature) in the same cute round pixel style as the reference rows, about 32 game pixels tall, stubby legs, big head, pink cheeks:'

describe() {
  case "$1" in
    rabbit)  echo "$ANIMAL a fluffy WHITE baby RABBIT with long upright ears with pink insides, a tiny pink nose and a round cotton tail.
$POSES" ;;
    chick)   echo "$ANIMAL a round fluffy YELLOW baby CHICK with a tiny orange beak, two tiny wings as arms and small orange feet, a little tuft of fluff on its head.
$POSES" ;;
    fox)     echo "$ANIMAL an ORANGE baby FOX KIT with a cream face and chest, big pointed ears with dark tips, a big fluffy tail with a white tip curling beside it.
$POSES" ;;
    alpaca)  echo "$ANIMAL a fluffy CREAM-white baby ALPACA with a woolly cloud-like head tuft, a long fluffy neck, small banana-shaped ears and a gentle sleepy smile.
$POSES" ;;
    kitten)  echo "$ANIMAL a GINGER-and-white TABBY baby KITTEN with darker orange stripes on its forehead and back, white muzzle and paws, a striped tail held up.
$POSES" ;;
    puppy)   echo "$ANIMAL a tan-and-cream baby SHIBA PUPPY with small triangle ears, a cream muzzle and belly, a curled-up tail on its back.
$POSES" ;;
    lamb)    echo "$ANIMAL a baby LAMB with a fluffy WHITE curly wool body, a soft grey face and grey ears, little dark hooves.
$POSES" ;;
    duckling) echo "$ANIMAL a baby DUCKLING, soft yellow with a pale orange flat bill, tiny wings, orange webbed feet, a small curl of fluff on its head.
$POSES" ;;
    # 소품 — 한 줄에 여섯. 사물만(얼굴 없음)
    items1) echo 'Draw ONLY small game items (objects, NOT characters — NO faces, NO eyes anywhere), each about 16 game pixels tall, chunky and readable at small size.
Exactly 6 sprites, left to right:
1) a small wooden FOOD BOWL heaped with green grass and a carrot
2) a glowing crystal SHARD: a small pointed violet-and-pale-blue crystal with a tiny gold star glint (the farm currency)
3) a short WOODEN FENCE segment (two posts, two rails)
4) a tiny cozy ANIMAL HOUSE: wooden hut with a red roof and a round door
5) a round blue WATER BOWL with water and a highlight
6) an AUTOMATIC FEEDER: a wooden hopper box on legs with a small tray of seeds' ;;
    items2) echo 'Draw ONLY small game items (objects, NOT characters — NO faces, NO eyes anywhere), each about 16 game pixels tall, chunky and readable at small size.
Exactly 6 sprites, left to right:
1) a STARLIGHT CURTAIN: a small arch frame with a midnight-blue curtain sprinkled with tiny gold stars (the breeding nest)
2) a STAR SEED: a small round seed with a gold star-shaped sprout
3) a STUDY LUNCHBOX: a small two-tier bento box wrapped in a checkered cloth with a knot on top
4) a WATER-LIGHT EGG: a pale aqua egg with wavy lighter blue stripes and a soft shine
5) a MESSAGE IN A BOTTLE: a small corked glass bottle with a rolled paper scroll inside
6) a small FLOWER patch: three little flowers (pink, yellow, white) on green leaves' ;;
    # 뼈대 개편(2026-11-06, 참고 게임 구조) — 똥·치료제·시설 셋·땅에 놓는 먹이
    items3) echo 'Draw ONLY small game items (objects, NOT characters — NO faces, NO eyes anywhere), each about 16 game pixels tall, chunky and readable at small size.
Exactly 6 sprites, left to right:
1) a small cute swirl of animal POOP, soft brown with a tiny highlight (cartoonish, not gross)
2) a small round MEDICINE bottle: a glass potion with pink liquid and a white cross label
3) a MAGIC BROOM standing upright: wooden handle with a small gold star charm, straw bristles with a faint sparkle
4) a FIREFLY JAR: a small glass jar with a cork lid and three glowing yellow fireflies inside
5) a PIGEON FEEDER: a small wooden birdhouse-shaped box on a pole with a seed tray and a tiny blue postal flag
6) a small pile of animal FOOD on the ground: a carrot and a few green leaves' ;;
    # 배경 층(2026-11-06, 참고 게임처럼 낮은 띠 그림을 겹친다) — 먼·중간·가까운 층 셋을 한 장에 위아래로
    bg_meadow) echo "$BGHEAD
1) TOP panel = FAR layer: soft lavender-blue distant rolling hills, very simple, lower half of the panel only.
2) MIDDLE panel = MID layer: rounded green hills with a few small round trees, lower two-thirds of the panel.
3) BOTTOM panel = NEAR layer: grass tufts, a few tiny pink and yellow flowers and small stones along a flat green ground line at the very bottom edge." ;;
    bg_academy) echo "$BGHEAD
1) TOP panel = FAR layer: distant pale-violet silhouette of a fairy-tale magic academy: castle towers, a library roof and an observatory dome with a telescope, lower half of the panel only.
2) MIDDLE panel = MID layer: dark starry-blue trimmed hedges and two small old street lamps with warm light, lower half of the panel.
3) BOTTOM panel = NEAR layer: flower beds with tiny golden star-shaped flowers and soft green grass along a flat ground line at the very bottom edge." ;;
    bg_drowned) echo "$BGHEAD
1) TOP panel = FAR layer: a calm pale-blue sea horizon with one tall stacked tower made of many different floors far away and a tiny airship in the sky, lower half of the panel only.
2) MIDDLE panel = MID layer: gentle light-blue water waves with a few floating wooden planks and a bottle, lower third of the panel.
3) BOTTOM panel = NEAR layer: a sandy shore with reeds, small shells and pebbles along a flat sandy ground line at the very bottom edge." ;;
    bg_isekai) echo "$BGHEAD
1) TOP panel = FAR layer: a muted dusk-blue city skyline of office buildings with a few lit windows, lower two-thirds of the panel only.
2) MIDDLE panel = MID layer: round street trees and a small bus stop sign, lower half of the panel.
3) BOTTOM panel = NEAR layer: a neat sidewalk hedge and short grass along a flat ground line at the very bottom edge." ;;
    # 방문자 — 세계의 틈에서 오는 이들
    visitors) echo 'Draw ONE row of three small visitors in the same cute round pixel style as the reference rows, each about 34 game pixels tall:
Exactly 3 sprites, left to right:
1) a plump round CARRIER PIGEON courier with a small brown leather satchel across its body and a tiny blue postal cap, holding a sealed letter with a red wax seal
2) a small round chibi OFFICE WORKER character (round head, neat dark hair, navy suit with a red tie, an ID badge on a lanyard) holding a clipboard with papers — friendly, polite smile
3) a tiny wooden AIRSHIP: a round cream balloon with brown stripes above a small wooden boat-shaped gondola with a little propeller (object only, no face)' ;;
  esac
}

ALL='rabbit chick fox alpaca kitten puppy lamb duckling items1 items2 items3 visitors bg_meadow bg_academy bg_drowned bg_isekai'
for name in ${@:-$ALL}; do
  target="$OUT/$name-raw.png"
  [ -f "$target" ] && { echo "skip $target"; continue; }
  prompt="$OUT/prompt-$name.txt"
  {
    echo 'Use the image generation tool to create ONE image. Do not write code.'
    echo
    echo 'MOST IMPORTANT: the background must be ONE flat solid color, pure magenta #FF00FF, filling the whole image edge to edge. NOT black, NOT dark, NO glow, NO halo, NO vignette, NO lighting effects, NO shadows around the sprites.'
    echo
    echo 'The attached reference sheet shows a family of original virtual-pet characters. Match their pixel-art style exactly, but draw the new subject described below.'
    echo
    describe "$name"
    echo
    case "$name" in bg_*) ;; *) echo "$COMMON" ;; esac          # 배경은 «한 줄 스프라이트» 배치가 아니다
  } > "$prompt"
  stamp="$OUT/.stamp-$name"; touch "$stamp"
  codex exec --skip-git-repo-check -i "$REF" < "$prompt" > "$OUT/$name.log" 2>&1
  made=$(find "$CODEX_HOME/generated_images" -newer "$stamp" -name '*.png' 2>/dev/null | head -1)
  if [ -n "$made" ]; then cp "$made" "$target"; echo "made $target"; else echo "FAILED $name (see $OUT/$name.log)"; fi
done
