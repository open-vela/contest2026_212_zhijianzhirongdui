/****************************************************************************
 * boards/xtensa/esp32s3/xiao-esp32s3-sense/src/esp32s3_camera_dma.h
 *
 * SPDX-License-Identifier: Apache-2.0
 ****************************************************************************/

#ifndef __BOARDS_XTENSA_ESP32S3_XIAO_ESP32S3_SENSE_SRC_ESP32S3_CAMERA_DMA_H
#define __BOARDS_XTENSA_ESP32S3_XIAO_ESP32S3_SENSE_SRC_ESP32S3_CAMERA_DMA_H

#include <stdint.h>

int  esp32s3_camera_dma_init(void);
void esp32s3_camera_dma_status(void);
void esp32s3_camera_dma_invalidate(void);
uint8_t *esp32s3_camera_dma_get_buffer(void);

#endif /* __BOARDS_XTENSA_ESP32S3_XIAO_ESP32S3_SENSE_SRC_ESP32S3_CAMERA_DMA_H */
