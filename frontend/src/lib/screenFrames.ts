export const SCREEN_THUMB_WIDTH = 64;
export const SCREEN_THUMB_HEIGHT = 36;
export const SCREEN_CHANGE_THRESHOLD = 12;

export function downsampleToGrayscale(
  rgba: Uint8ClampedArray,
  srcWidth: number,
  srcHeight: number,
): number[] {
  const out: number[] = new Array(SCREEN_THUMB_WIDTH * SCREEN_THUMB_HEIGHT);
  if (srcWidth <= 0 || srcHeight <= 0 || rgba.length === 0) {
    out.fill(0);
    return out;
  }
  for (let y = 0; y < SCREEN_THUMB_HEIGHT; y++) {
    const srcY = Math.min(srcHeight - 1, Math.floor((y * srcHeight) / SCREEN_THUMB_HEIGHT));
    for (let x = 0; x < SCREEN_THUMB_WIDTH; x++) {
      const srcX = Math.min(srcWidth - 1, Math.floor((x * srcWidth) / SCREEN_THUMB_WIDTH));
      const i = (srcY * srcWidth + srcX) * 4;
      out[y * SCREEN_THUMB_WIDTH + x] = (rgba[i] + rgba[i + 1] + rgba[i + 2]) / 3;
    }
  }
  return out;
}

export function meanAbsoluteDiff(a: number[], b: number[]): number {
  const length = Math.min(a.length, b.length);
  if (length === 0) return 0;
  let total = 0;
  for (let i = 0; i < length; i++) {
    total += Math.abs(a[i] - b[i]);
  }
  return total / length;
}

export function isScreenChanged(previous: number[] | null, next: number[]): boolean {
  if (previous === null) return true;
  return meanAbsoluteDiff(previous, next) > SCREEN_CHANGE_THRESHOLD;
}
