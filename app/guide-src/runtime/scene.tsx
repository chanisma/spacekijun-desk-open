/* eslint-disable react-refresh/only-export-components */
/**
 * Scene — 결정론적 씬 타임라인.
 *
 * presentation 프로젝트(`src/scene/index.tsx`)에서 옮겨 왔다. **타임라인 수학
 * (`interpolate`/`spring`/`riseIn`)은 한 글자도 바꾸지 않았다** — 저쪽에서 저작한 씬
 * 코드를 그대로 붙여 넣을 수 있어야 하기 때문이다(`software-walkthrough-builder` 스킬).
 *
 * ── 바꾼 것 하나: 시계의 주인 ──────────────────────────────────────────────
 * 원본은 덱 엔진의 `useDeck().isStatic` 을 읽어 "썸네일이면 t 를 고정" 했다.
 * 여기엔 덱 엔진이 없고 **모달 안에서 한 단계씩 재생**하므로, 대신
 *   `playKey`  — 값이 바뀌면 t 가 0 부터 다시 흐른다(단계 이동·다시 재생)
 *   `paused`   — 정지(모달이 닫혀 있을 때 rAF 를 돌리지 않는다)
 * 를 받는다. 모션이 "경과 시간 t 의 순수 함수" 라는 원칙은 그대로다.
 *
 * ── CSS 변수 ───────────────────────────────────────────────────────────────
 * 씬 코드는 `var(--primary)` 같은 덱 토큰을 쓴다. 그 토큰은 `WalkthroughStage` 가
 * 자기 루트에 정의한다 — 여기서 정의하면 씬을 감싸는 화면마다 달라질 수 없다.
 */
import {
  createContext,
  useContext,
  useEffect,
  useState,
  type CSSProperties,
  type ReactNode,
} from 'react';

const SceneTimeCtx = createContext(9999);

/** 씬 시작 후 경과 초. `<Scene>` 안에서만 유효 */
export function useSceneTime(): number {
  return useContext(SceneTimeCtx);
}

export function Scene({
  children,
  playKey,
  paused = false,
  freezeAt = 9999,
  className,
  style,
}: {
  children: ReactNode;
  /** 값이 바뀌면 처음부터 다시 재생한다(단계 이동·다시 재생 버튼) */
  playKey?: string | number;
  /** 정지 — t 를 `freezeAt` 에 고정한다(모달이 닫혀 있을 때 rAF 낭비 방지) */
  paused?: boolean;
  /** 정지 상태에서 고정할 t. 기본은 모든 모션이 끝난 상태 */
  freezeAt?: number;
  className?: string;
  style?: CSSProperties;
}) {
  const [t, setT] = useState(paused ? freezeAt : 0);

  useEffect(() => {
    if (paused) {
      setT(freezeAt);
      return;
    }
    // playKey 가 바뀌면 이 effect 가 다시 돌며 t0 가 갱신된다 = 처음부터 재생
    setT(0);
    let raf = 0;
    const t0 = performance.now();
    const loop = (now: number) => {
      setT((now - t0) / 1000);
      raf = requestAnimationFrame(loop);
    };
    raf = requestAnimationFrame(loop);
    return () => cancelAnimationFrame(raf);
  }, [paused, freezeAt, playKey]);

  return (
    <SceneTimeCtx.Provider value={t}>
      <div
        className={className}
        style={{ position: 'relative', width: '100%', height: '100%', ...style }}
      >
        {children}
      </div>
    </SceneTimeCtx.Provider>
  );
}

/* ── 타임라인 수학 (presentation 원본과 동일 — 저작 호환) ── */

/** t를 [tin0,tin1] → [tout0,tout1]로 사상 (기본 clamp) */
export function interpolate(
  t: number,
  tin: [number, number],
  tout: [number, number],
  ease?: (x: number) => number,
): number {
  let x = (t - tin[0]) / (tin[1] - tin[0]);
  x = Math.max(0, Math.min(1, x));
  if (ease) x = ease(x);
  return tout[0] + (tout[1] - tout[0]) * x;
}

export const easeOut = (x: number) => 1 - Math.pow(1 - x, 3);
export const easeInOut = (x: number) =>
  x < 0.5 ? 4 * x * x * x : 1 - Math.pow(-2 * x + 2, 3) / 2;

/** 오버슈트 스프링: delay 후 duration 동안 0→1 (살짝 튕김) */
export function spring(t: number, delay = 0, duration = 0.8): number {
  const x = Math.max(0, Math.min(1, (t - delay) / duration));
  if (x === 0 || x === 1) return x;
  return 1 - Math.exp(-6 * x) * Math.cos(12 * x) * (1 - x);
}

/** spring 진입 헬퍼 — opacity + translateY를 한 번에 */
export function riseIn(
  t: number,
  delay = 0,
  duration = 0.8,
  distance = 26,
): CSSProperties {
  const s = spring(t, delay, duration);
  return {
    opacity: Math.min(1, s * 1.4),
    transform: `translateY(${(1 - s) * distance}px)`,
  };
}
