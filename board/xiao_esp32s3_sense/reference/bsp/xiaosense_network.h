/* XIAO Sense — Network upload with MQTT auth */

#ifndef __XIAO_NETWORK_H
#define __XIAO_NETWORK_H
#include <nuttx/config.h>
#include <stdint.h>
#ifdef CONFIG_ESP32S3_WIFI
int  network_init(void);
int  network_send_embedding(const float *embedding, int dim);
int  network_send_status(const char *status);
int  network_check_commands(void);
int  network_send_json(const char *json, int len);

/* Silhouette: compact binary format over MQTT
 * Format: [4B magic "SILH"][2B w][2B h][2B thresh][2B fg_px][2B rle_cnt][N*2B rle LE]
 * Returns 0 on success, <0 on error. */
int  network_send_silhouette(const uint16_t *rle, uint16_t rle_count,
                              uint16_t width, uint16_t height,
                              uint8_t threshold, uint16_t fg_pixels);
#endif
#endif
