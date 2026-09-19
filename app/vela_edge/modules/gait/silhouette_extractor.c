/****************************************************************************
 * boards/xtensa/esp32s3/xiao-esp32s3-sense/src/silhouette_extractor.c
 * v8.4 — Frame differencing + Otsu thresholding + RLE silhouette extraction
 *
 * Designed for corridor gait capture: fixed camera, walking person,
 * controlled indoor lighting. No ML model needed — pure C arithmetic.
 *
 * Algorithm per frame:
 *   1. RGB565 → grayscale (ITU-R BT.601)
 *   2. absdiff with previous grayscale frame
 *   3. Otsu threshold OR fixed threshold → binary mask
 *   4. Run-length encode binary mask → compact representation for MQTT
 *
 * Timing (ESP32-S3 @ 240MHz, QQVGA 160×102 from 32KB DMA buffer):
 *   - RGB565→Gray:     ~4ms
 *   - absdiff:         ~2ms
 *   - Otsu histogram:  ~3ms
 *   - Threshold + RLE: ~2ms
 *   - Total:           ~11ms per frame
 ****************************************************************************/

#include "silhouette_extractor.h"
#include <string.h>

/* ---- Static state ---- */

static uint16_t g_width  = 160;
static uint16_t g_height = 102;   /* 32KB DMA / (160*2) = 102 rows */
static uint16_t g_pixels = 16320; /* w*h */

/* Frame buffers — allocated statically to guarantee SRAM placement */
static uint8_t  g_prev_gray[16320];           /* previous frame grayscale */
static uint8_t  g_diff[16320];                /* absdiff result */
static uint16_t g_rle[SIL_RLE_MAX_PAIRS * 2]; /* RLE output: [bg,fg,bg,fg,...] */
static uint16_t g_rle_count = 0;
static uint8_t  g_threshold   = SIL_DIFF_THRESHOLD;
static uint16_t g_motion_px   = 0;
static bool     g_warmed_up   = false;        /* first frame is warm-up only */

/* ---- Internal helpers ---- */

/* Convert RGB565 pixel to 8-bit grayscale (ITU-R BT.601 luma).
 * RGB565 layout: RRRRR GGGGGG BBBBB (MSB first)
 * Y = 0.299R' + 0.587G' + 0.114B'
 * Integer: (R5*77 + G6*150 + B5*29 + 128) >> 8 */
static inline uint8_t rgb565_to_gray(uint16_t px)
{
  uint8_t r5 = (px >> 11) & 0x1F;
  uint8_t g6 = (px >> 5)  & 0x3F;
  uint8_t b5 =  px        & 0x1F;
  return ((uint32_t)r5 * 77 + (uint32_t)g6 * 150 + (uint32_t)b5 * 29 + 128) >> 8;
}

#if SIL_OTSU_ENABLED

/* Otsu's method: find threshold maximizing between-class variance.
 * Operates on g_diff[] histogram. Returns 0..255.
 * Complexity: O(256) after O(N) histogram build. */
static uint8_t otsu_threshold(const uint8_t *diff, uint16_t n)
{
  uint32_t hist[256] = {0};
  uint32_t total = n;
  uint32_t sum = 0;

  /* Build histogram */
  for (uint16_t i = 0; i < n; i++) {
    hist[diff[i]]++;
    sum += diff[i];
  }

  /* Otsu iteration */
  uint32_t w0 = 0;
  uint64_t sum0 = 0;
  uint64_t max_var = 0;
  uint8_t  best_t = 0;

  for (uint16_t t = 0; t < 255; t++) {
    w0   += hist[t];
    if (w0 == 0) continue;
    if (w0 == total) break;

    sum0 += (uint32_t)t * hist[t];
    uint32_t w1 = total - w0;
    uint64_t sum1 = sum - sum0;

    /* σ² = w0*w1*(μ0-μ1)² = sum0²/w0 + sum1²/w1 (minus constant) */
    uint64_t var = sum0 * sum0 / w0 + sum1 * sum1 / w1;

    if (var > max_var) {
      max_var = var;
      best_t = (uint8_t)t;
    }
  }

  return best_t;
}
#endif /* SIL_OTSU_ENABLED */

/* Run-length encode binary mask.
 * Scans row-major, packs into (bg_run, fg_run) pairs.
 * Always starts with background run.
 * Mask format: 1 = foreground (silhouette), 0 = background.
 * Returns: number of uint16_t entries written. 0 on overflow. */
static uint16_t rle_encode(const uint8_t *mask, uint16_t pixels,
                            uint16_t *rle_out)
{
  uint16_t pair_idx = 0;
  uint8_t  cur_bit = 0;       /* start with background */
  uint16_t run_len = 0;

  /* If mask starts with 1 (foreground), insert bg_run=0 first */
  if (mask[0] & 0x80) {
    if (pair_idx >= SIL_RLE_MAX_PAIRS * 2) return 0;
    rle_out[pair_idx++] = 0;  /* bg_run = 0 */
  }

  for (uint16_t i = 0; i < pixels; i++) {
    uint8_t byte_idx = i >> 3;
    uint8_t bit_idx  = 7 - (i & 7);  /* MSB first within byte */
    uint8_t bit      = (mask[byte_idx] >> bit_idx) & 1;

    if (bit == cur_bit) {
      run_len++;
    } else {
      if (pair_idx >= SIL_RLE_MAX_PAIRS * 2) return 0;  /* overflow */
      rle_out[pair_idx++] = run_len;
      cur_bit = bit;
      run_len = 1;
    }
  }

  /* Final run */
  if (pair_idx >= SIL_RLE_MAX_PAIRS * 2) return 0;
  rle_out[pair_idx++] = run_len;

  return pair_idx;
}

/* ---- Public API ---- */

void silhouette_extractor_init(uint16_t width, uint16_t height)
{
  g_width  = width;
  g_height = height;
  g_pixels = width * height;

  /* Clear everything */
  memset(g_prev_gray, 0, sizeof(g_prev_gray));
  memset(g_diff, 0, sizeof(g_diff));
  memset(g_rle, 0, sizeof(g_rle));
  g_rle_count = 0;
  g_threshold = SIL_DIFF_THRESHOLD;
  g_motion_px = 0;
  g_warmed_up = false;
}

/* Warm-up: fill prev_gray with first frame, no processing.
 * Call internally on first process() call. */
static void silhouette_warm_up(const uint8_t *rgb565_buf)
{
  const uint16_t *px16 = (const uint16_t *)rgb565_buf;
  uint16_t n = g_pixels;
  for (uint16_t i = 0; i < n; i++) {
    g_prev_gray[i] = rgb565_to_gray(px16[i]);
  }
  g_warmed_up = true;
}

bool silhouette_extractor_process(const uint8_t *rgb565_buf)
{
  /* First call: warm-up only — fill prev_gray, skip processing */
  if (!g_warmed_up) {
    silhouette_warm_up(rgb565_buf);
    g_motion_px = 0;
    g_threshold = 0;
    g_rle_count = 0;
    return false;
  }

  const uint16_t *px16 = (const uint16_t *)rgb565_buf;
  uint16_t n = g_pixels;

  /* Step 1: Convert to grayscale + compute absdiff with previous frame */
  for (uint16_t i = 0; i < n; i++) {
    uint8_t gray = rgb565_to_gray(px16[i]);
    int16_t d = (int16_t)gray - (int16_t)g_prev_gray[i];
    if (d < 0) d = -d;
    g_diff[i] = (uint8_t)d;
    g_prev_gray[i] = gray;  /* update for next frame */
  }

  /* Step 2: Determine threshold */
#if SIL_OTSU_ENABLED
  g_threshold = otsu_threshold(g_diff, n);
#else
  g_threshold = SIL_DIFF_THRESHOLD;
#endif

  /* Step 3: Build binary mask (packed bits) + count motion pixels */
  uint16_t motion_count = 0;
  uint16_t mask_bytes = (n + 7) / 8;

  /* Write mask over g_diff (destructive reuse — done after Otsu) */
  for (uint16_t byte_i = 0; byte_i < mask_bytes; byte_i++) {
    g_diff[byte_i] = 0;  /* init byte */
  }

  for (uint16_t i = 0; i < n; i++) {
    if (g_diff[i] > g_threshold) {
      uint16_t byte_idx = i >> 3;
      uint8_t  bit_pos  = 7 - (i & 7);
      g_diff[byte_idx] |= (1 << bit_pos);
      motion_count++;
    }
    /* else: bit stays 0 (already cleared in init loop above) */
  }

  g_motion_px = motion_count;

  /* Step 4: RLE encode (mask is now in g_diff[]) */
  g_rle_count = rle_encode(g_diff, n, g_rle);
  if (g_rle_count == 0 && motion_count > 0) {
    /* RLE overflow: signal with count=0xFFFF */
    g_rle_count = 0xFFFF;
  }

  /* Step 5: Motion detection — require >1% of pixels changed */
  return (motion_count > (n / 100));
}

/* ---- Accessors ---- */

const uint16_t *silhouette_get_rle(void)
{
  return g_rle;
}

uint16_t silhouette_get_rle_count(void)
{
  return g_rle_count;
}

uint8_t silhouette_get_threshold(void)
{
  return g_threshold;
}

uint16_t silhouette_get_motion_pixels(void)
{
  return g_motion_px;
}

uint16_t silhouette_get_width(void)
{
  return g_width;
}

uint16_t silhouette_get_height(void)
{
  return g_height;
}

uint8_t silhouette_get_mask_byte(uint16_t byte_offset)
{
  uint16_t mask_bytes = (g_pixels + 7) / 8;
  if (byte_offset >= mask_bytes) return 0;
  return g_diff[byte_offset];
}
