/* inference_task.c — Message-queue based ML inference pipeline
 *
 * Task 3: Decoupled architecture
 *   [Camera DMA] → mqueue → [Inference Task] → mqueue → [Main Task → MQTT]
 *
 * Task 4: Two-stage pipeline
 *   Stage 1: face_region_filter() — lightweight motion-in-center heuristic
 *   Stage 2: face_embedding_run() — MobileFaceNet INT8 → 128-d embedding
 */

#include <nuttx/config.h>

#ifdef CONFIG_TFLITEMICRO

#include <stdio.h>
#include <string.h>
#include <stdlib.h>
#include <pthread.h>
#include <mqueue.h>
#include <errno.h>
#include <unistd.h>
#include <fcntl.h>

#include "inference_task.h"
#include "face_embedding.h"

/* Message queue names */
#define INFER_MQ_NAME   "infer_q"
#define RESULT_MQ_NAME  "result_q"

/* Queue depths */
#define INFER_MQ_MAXMSG  4
#define RESULT_MQ_MAXMSG 4

/* Inference throttle: minimum ms between inferences */
#define INFER_THROTTLE_MS  500

/* Skip Stage 1 pre-filter for high-load testing.
 * Set to 1 to bypass face_region_filter and always run MobileFaceNet. */
#define SKIP_STAGE1_FILTER  0

/* Face region: center 80x80 of 160x120 frame */
#define FACE_CX  80
#define FACE_CY  60
#define FACE_HW  40   /* half-width of face ROI */
#define FACE_HH  40   /* half-height of face ROI */
#define FACE_MOTION_MIN  50  /* min foreground pixels in face region */

/* Frame descriptor sent via mqueue */
struct frame_req_s {
  uint32_t frame_id;
  const uint8_t *buf;  /* DMA buffer pointer (caller owns memory) */
};

/* Result sent back via mqueue */
struct result_s {
  uint32_t frame_id;
  float embedding[128];
  int valid;  /* 1 = valid embedding, 0 = failed */
};

static mqd_t g_infer_mq  = (mqd_t)-1;
static mqd_t g_result_mq = (mqd_t)-1;
static pthread_t g_infer_thread;
static volatile bool g_infer_running = false;

/* Two-stage pre-filter: check if face region has sufficient motion */
int face_region_filter(const uint8_t *buf)
{
  if (!buf) return 0;

  int motion = 0;
  /* Sample center region of the 160x120 RGB565 frame.
   * Check every 4th pixel for performance. */
  for (int y = FACE_CY - FACE_HH; y < FACE_CY + FACE_HH; y += 4) {
    for (int x = FACE_CX - FACE_HW; x < FACE_CX + FACE_HW; x += 4) {
      int idx = (y * 160 + x) * 2;
      uint16_t px = buf[idx] | (buf[idx+1] << 8);
      /* Simple skin-like check: R > G > B (approximate) */
      int r = (px >> 11) & 0x1F;
      int g = (px >> 5)  & 0x3F;
      int b = px & 0x1F;
      if (r > (g >> 1) && r > b) {
        motion++;
      }
    }
  }
  return (motion >= FACE_MOTION_MIN) ? 1 : 0;
}

/* Inference worker thread */
static void *inference_worker(void *arg)
{
  struct frame_req_s req;
  struct result_s result;
  unsigned int prio;
  int ret;

  printf("INFER: worker started\n");
  g_infer_running = true;

  while (g_infer_running) {
    /* Block waiting for frame */
    ret = mq_receive(g_infer_mq, (char *)&req, sizeof(req), &prio);
    if (ret < 0) {
      if (errno == EINTR) continue;
      printf("INFER: mq_receive err=%d\n", errno);
      break;
    }

    /* Stage 1: face region pre-filter (can be skipped for load testing) */
#if !SKIP_STAGE1_FILTER
    if (!face_region_filter(req.buf)) {
      /* No face detected — skip heavy inference, return invalid */
      result.frame_id = req.frame_id;
      result.valid = 0;
      mq_send(g_result_mq, (const char *)&result, sizeof(result), 0);
      continue;
    }
#endif

    /* Stage 2: MobileFaceNet inference */
    memset(&result, 0, sizeof(result));
    result.frame_id = req.frame_id;
    ret = face_embedding_run(result.embedding);
    result.valid = (ret == 0) ? 1 : 0;

    if (result.valid) {
      printf("INFER: frame %lu emb[0]=%.4f\n",
             (unsigned long)req.frame_id, result.embedding[0]);
    }

    /* Throttle: ensure minimum interval between inferences */
    usleep(INFER_THROTTLE_MS * 1000);

    /* Send result back */
    mq_send(g_result_mq, (const char *)&result, sizeof(result), 0);
  }

  printf("INFER: worker stopped\n");
  return NULL;
}

/* Initialize inference task */
int inference_task_init(void)
{
  struct mq_attr attr;
  pthread_attr_t pattr;
  int ret;

  /* Create frame input queue */
  attr.mq_maxmsg  = INFER_MQ_MAXMSG;
  attr.mq_msgsize = sizeof(struct frame_req_s);
  attr.mq_flags   = 0;

  g_infer_mq = mq_open(INFER_MQ_NAME, O_RDWR | O_CREAT, 0666, &attr);
  if (g_infer_mq == (mqd_t)-1) {
    printf("INFER: mq_open(infer) err=%d\n", errno);
    return -1;
  }

  /* Create result output queue */
  attr.mq_maxmsg  = RESULT_MQ_MAXMSG;
  attr.mq_msgsize = sizeof(struct result_s);

  g_result_mq = mq_open(RESULT_MQ_NAME, O_RDWR | O_CREAT, 0666, &attr);
  if (g_result_mq == (mqd_t)-1) {
    printf("INFER: mq_open(result) err=%d\n", errno);
    mq_close(g_infer_mq);
    return -1;
  }

  /* Create worker thread */
  pthread_attr_init(&pattr);
  pthread_attr_setstacksize(&pattr, 8192);

  ret = pthread_create(&g_infer_thread, &pattr,
                       inference_worker, NULL);
  if (ret != 0) {
    printf("INFER: pthread_create err=%d\n", ret);
    mq_close(g_infer_mq);
    mq_close(g_result_mq);
    return -1;
  }

  pthread_setname_np(g_infer_thread, "inference");
  printf("INFER: task initialized (queues + thread)\n");
  return 0;
}

/* Submit frame for inference (non-blocking) */
int inference_submit_frame(const uint8_t *buf)
{
  struct frame_req_s req;
  static uint32_t s_frame_id = 0;

  if (g_infer_mq == (mqd_t)-1 || !buf) return -1;

  req.frame_id = ++s_frame_id;
  req.buf = buf;

  int ret = mq_send(g_infer_mq, (const char *)&req, sizeof(req), 0);
  if (ret < 0) {
    /* Queue full — drop frame (non-blocking design) */
    return -1;
  }
  return 0;
}

/* Get inference result (non-blocking) */
int inference_get_result(float embedding[128])
{
  struct result_s result;
  unsigned int prio;
  struct timespec ts = {0, 0};  /* immediate timeout */

  if (g_result_mq == (mqd_t)-1) return 0;

  int ret = mq_timedreceive(g_result_mq, (char *)&result,
                            sizeof(result), &prio, &ts);
  if (ret < 0) return 0;  /* no result available */

  if (result.valid && embedding) {
    memcpy(embedding, result.embedding, 128 * sizeof(float));
  }
  return result.valid;
}

#endif /* CONFIG_TFLITEMICRO */
