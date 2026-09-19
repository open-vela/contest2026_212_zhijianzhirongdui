/****************************************************************************
 * boards/xtensa/esp32s3/xiao-esp32s3-sense/src/silhouette_extractor.h
 * v8.4 — Frame differencing silhouette extraction for corridor gait capture.
 *
 * Pipeline: RGB565 DMA frame → grayscale → absdiff → Otsu threshold → RLE
 *
 * Memory footprint (QQVGA 160×120):
 *   - prev_gray: 19,200 bytes (SRAM)
 *   - diff_buf:  19,200 bytes (SRAM, reused for otab)
 *   - rle_out:    ~2,400 uint16_t pairs max = 4,800 bytes (SRAM)
 *   - Total:     ~43 KB
 ****************************************************************************/

#ifndef __SILHOUETTE_EXTRACTOR_H
#define __SILHOUETTE_EXTRACTOR_H

#include <stdint.h>
#include <stdbool.h>

/* ---- Configuration ---- */

/* Fixed threshold mode: diff > SIL_DIFF_THRESHOLD → foreground
 * Good for controlled indoor lighting. Set to 0 to always use Otsu. */
#define SIL_DIFF_THRESHOLD  30

/* Otsu mode: compute optimal threshold per-frame (more robust, ~3ms on 240MHz) */
#define SIL_OTSU_ENABLED    1

/* RLE output: alternate bg/fg run lengths */
#define SIL_RLE_MAX_PAIRS   1600    /* worst case: alternating every pixel on a row */

/* ---- API ---- */

/* Initialize for given frame dimensions.
 * Call once at boot. Allocates internal buffers statically. */
void silhouette_extractor_init(uint16_t width, uint16_t height);

/* Process a new RGB565 frame from DMA buffer.
 * Returns true if sufficient motion was detected (pixels > w*h/100).
 * rgb565_buf: pointer to start of DMA buffer (must be in valid memory). */
bool silhouette_extractor_process(const uint8_t *rgb565_buf);

/* Get the RLE-encoded silhouette.
 * Format: array of uint16_t pairs [(bg_run, fg_run), ...]
 * Always starts with background run. If mask starts with foreground,
 * first bg_run = 0.
 * Returns: pointer to internal RLE buffer (valid until next process() call). */
const uint16_t *silhouette_get_rle(void);

/* Number of uint16_t entries in the RLE (not pairs — total entries). */
uint16_t silhouette_get_rle_count(void);

/* Per-frame statistics. */
uint8_t  silhouette_get_threshold(void);      /* threshold used this frame */
uint16_t silhouette_get_motion_pixels(void);  /* foreground pixel count */
uint16_t silhouette_get_width(void);
uint16_t silhouette_get_height(void);

/* Debug: get raw binary mask byte (mask is packed bits, row-major).
 * byte_offset: 0 to (width*height/8 - 1). Returns 1 byte. */
uint8_t silhouette_get_mask_byte(uint16_t byte_offset);

#endif /* __SILHOUETTE_EXTRACTOR_H */
