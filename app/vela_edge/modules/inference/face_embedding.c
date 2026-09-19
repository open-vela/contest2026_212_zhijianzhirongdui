/* face_embedding.c — v8.16: cache-safe inference with full dcache sync */

#include "tflm_wrapper.h"
#include "xiaosense_network.h"
#include <string.h>
#include <stdio.h>
#include <unistd.h>
#include <nuttx/cache.h>

#define FACE_SIZE  112
#define IMG_W      160
#define IMG_H      102

extern uint8_t *esp32s3_camera_dma_get_buffer(void);
extern void esp32s3_camera_dma_invalidate(void);

static void crop_preprocess(const uint8_t *dma_buf, int8_t *face_out)
{
  int sx = (IMG_W - FACE_SIZE) / 2, sy = (IMG_H - FACE_SIZE) / 2;
  for (int y = 0; y < FACE_SIZE; y++) {
    int src_y = sy + y;
    for (int x = 0; x < FACE_SIZE; x++) {
      int dst = (y * FACE_SIZE + x) * 3;
      if (src_y >= 0 && src_y < IMG_H) {
        int src = (src_y * IMG_W + (sx + x)) * 2;
        uint16_t p = (dma_buf[src+1]<<8) | dma_buf[src];
        face_out[dst+0] = (int8_t)((int)(((p>>11)&0x1F)<<3) - 128);
        face_out[dst+1] = (int8_t)((int)(((p>>5)&0x3F)<<2) - 128);
        face_out[dst+2] = (int8_t)((int)((p&0x1F)<<3) - 128);
      } else {
        face_out[dst+0] = face_out[dst+1] = face_out[dst+2] = 0;
      }
    }
  }
}

int face_embedding_run(float embedding[128])
{
  const uint8_t *dma_buf = esp32s3_camera_dma_get_buffer();
  if (!dma_buf) return -1;
  esp32s3_camera_dma_invalidate();

  void *in_ptr = tflm_get_input(0);
  int in_bytes = tflm_get_input_size(0);
  if (!in_ptr || in_bytes < FACE_SIZE*FACE_SIZE*3) return -2;

  int8_t *in_data = (int8_t *)in_ptr;
  crop_preprocess(dma_buf, in_data);

  /* Full cache flush before inference (ESP32-S3 errata CACHE-126 workaround) */
  up_clean_dcache_all();
  up_invalidate_dcache_all();

  int ret = tflm_invoke();
  if (ret != 0) return -3;

  /* Invalidate cache before reading INT8 output from PSRAM */
  up_invalidate_dcache_all();
  usleep(50000);

  const int8_t *out_i8 = (const int8_t *)tflm_get_output(0);
  int out_bytes = tflm_get_output_bytes(0);
  float scale = tflm_get_output_scale(0);
  int zp = tflm_get_output_zero_point(0);
  if (!out_i8 || out_bytes < 128) return -4;

  for (int i = 0; i < 128; i++)
    embedding[i] = ((float)out_i8[i] - (float)zp) * scale;
  return 0;
}
