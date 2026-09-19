/* inference_task.h — Message-queue based inference pipeline
 * Task 3: Decouples camera capture from ML inference using POSIX mqueue.
 * Task 4: Two-stage pipeline — silhouette pre-filter + MobileFaceNet.
 */

#ifndef __INFERENCE_TASK_H
#define __INFERENCE_TASK_H

#include <nuttx/config.h>

#ifdef CONFIG_TFLITEMICRO

/* Initialize inference task and message queues.
 * Returns 0 on success, -1 on failure. */
int inference_task_init(void);

/* Submit a frame for inference (non-blocking).
 * Returns 0 if queued, -1 if queue full.
 * buf: DMA buffer (160x120 RGB565), caller retains ownership until done. */
int inference_submit_frame(const uint8_t *buf);

/* Check if inference result is available (non-blocking).
 * Returns 1 if result ready, 0 if none.
 * embedding[128]: receives the 128-d float embedding. */
int inference_get_result(float embedding[128]);

/* Two-stage pre-filter: check if face region likely contains a face.
 * Uses simple center-region motion heuristic (no extra model needed).
 * buf: DMA buffer (160x120 RGB565)
 * Returns 1 if face likely present, 0 if not. */
int face_region_filter(const uint8_t *buf);

#endif /* CONFIG_TFLITEMICRO */
#endif /* __INFERENCE_TASK_H */
