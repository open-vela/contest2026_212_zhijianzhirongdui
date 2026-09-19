/****************************************************************************
 * boards/xtensa/esp32s3/xiao-esp32s3-sense/src/esp32s3_bringup.c
 *
 * SPDX-License-Identifier: Apache-2.0
 * v8.0 - Chained DMA 8×4KB=32KB, QQVGA-ready: bus_clk+rst, correct init sequence for XCLK
 *        Added: SYSTEM.perip_clk_en1(LCD_CAM), perip_rst_en1 toggle,
 *        LCD_CLOCK config before GPIO matrix, diagnostic readbacks
 * PSRAM: OCTAL (ESP32-S3R8), Camera SCCB: GPIO39/40, XCLK: LCD_CAM
 ****************************************************************************/

#include "xiao_esp32s3_regs.h"

#include <nuttx/config.h>

#include <stdio.h>
#include <fcntl.h>
#include <unistd.h>
#include <syslog.h>
#include <sys/stat.h>
#include <sys/ioctl.h>
#include <sys/types.h>
#include <debug.h>

#include <errno.h>
#include <nuttx/fs/fs.h>
#include <nuttx/clock.h>

#include <nuttx/video/ov3660.h>
#include "esp32s3_gpio.h"
#include "hardware/esp32s3_gpio_sigmap.h"

#ifdef CONFIG_ESP32S3_TIMER
#  include "esp32s3_board_tim.h"
#endif

#ifdef CONFIG_ESP32S3_WIFI
#  include "esp32s3_board_wlan.h"
#endif

#ifdef CONFIG_ESP32S3_BLE
#  include "esp32s3_ble.h"
#endif

#ifdef CONFIG_ESP32S3_WIFI_BT_COEXIST
#  include "esp32s3_wifi_adapter.h"
#endif

#ifdef CONFIG_ESP32S3_RT_TIMER
#  include "esp32s3_rt_timer.h"
#endif

#ifdef CONFIG_ESP32S3_I2C
#  include "esp32s3_i2c.h"
#endif

#ifdef CONFIG_WATCHDOG
#  include "esp32s3_board_wdt.h"
#endif

#ifdef CONFIG_INPUT_BUTTONS
#  include <nuttx/input/buttons.h>
#endif

#ifdef CONFIG_ESP32S3_SPI
#  include "esp32s3_spi.h"
#endif

#ifdef CONFIG_ESP32S3_SDMMC
#include "esp32s3_board_sdmmc.h"
#endif

#include "xiao-esp32s3-sense.h"
#include "esp32s3_camera_dma.h"
#ifdef CONFIG_ESP32S3_WIFI
#include "xiaosense_network.h"
#include "ble_scanner_nuttx.h"
#include "silhouette_extractor.h"
#include "inference_task.h"
#endif

/****************************************************************************
 * Public Functions
 ****************************************************************************/

int esp32s3_bringup(void)
{
  int ret;
  static int g_tflm_ready = 0;
  float emb[128];
  static float emb_buf[3][128];
  int face_ret = 0;

#ifdef CONFIG_FS_PROCFS
  ret = nx_mount(NULL, "/proc", "procfs", 0, NULL);
  if (ret < 0)
    syslog(LOG_ERR, "ERROR: Failed to mount procfs at /proc: %d\n", ret);
#endif

#ifdef CONFIG_FS_TMPFS
  ret = nx_mount(NULL, CONFIG_LIBC_TMPDIR, "tmpfs", 0, NULL);
  if (ret < 0)
    syslog(LOG_ERR, "ERROR: Failed to mount tmpfs at %s: %d\n",
           CONFIG_LIBC_TMPDIR, ret);
#endif

#ifdef CONFIG_ESP32S3_TIMER
  ret = board_tim_init();
  if (ret < 0)
    syslog(LOG_ERR, "Failed to initialize timers: %d\n", ret);
#endif

#ifdef CONFIG_ESP32S3_RT_TIMER
  ret = esp32s3_rt_timer_init();
  if (ret < 0)
    syslog(LOG_ERR, "Failed to initialize RT timer: %d\n", ret);
#endif

#ifdef CONFIG_WATCHDOG
  ret = board_wdt_init();
  if (ret < 0)
    syslog(LOG_ERR, "Failed to initialize watchdog timer: %d\n", ret);
#endif

#ifdef CONFIG_I2C_DRIVER
  /* GPIO39/40: Disable USB Serial/JTAG PHY to release pins for I2C/SCCB.
   * ESP32-S3 USB Serial/JTAG holds GPIO39/40 even after IO_MUX switch.
   * Clear USB_PAD_ENABLE (bit14) and USB_DEVICE_CLK_EN (bit10) per ESP-IDF. */
  modifyreg32(0x60038018, 1<<14, 0);  /* USB_SERIAL_JTAG_CONF0_REG */
  modifyreg32(0x600C001C, 1<<10, 0);  /* SYSTEM_PERIP_CLK_EN1_REG */

  /* GPIO39/40 diagnostic before I2C init */
  cam_debug("I2C_PRE GPIO39=0x%08lX GPIO40=0x%08lX\n",
         getreg32(IO_MUX_GPIO10), getreg32(0x600090A4));

  ret = board_i2c_init();

  cam_debug("I2C_POST ret=%d CTR=0x%08lX SR=0x%08lX\n",
         ret, getreg32(0x60013004), getreg32(0x60013008));

  if (ret < 0)
    syslog(LOG_ERR, "Failed to initialize I2C driver: %d\n", ret);
#endif

#ifdef CONFIG_INPUT_BUTTONS
  ret = btn_lower_initialize("/dev/buttons");
  if (ret < 0)
    syslog(LOG_ERR, "Failed to initialize button driver: %d\n", ret);
#endif

#ifdef CONFIG_ESP32S3_SPIFLASH
  ret = board_spiflash_init();
  if (ret)
    syslog(LOG_ERR, "ERROR: Failed to initialize SPI Flash\n");
#endif

#ifdef CONFIG_ESP32S3_WIRELESS
#ifdef CONFIG_ESP32S3_WIFI_BT_COEXIST
  ret = esp32s3_wifi_bt_coexist_init();
  if (ret)
    syslog(LOG_ERR, "ERROR: Failed to initialize Wi-Fi and BT coexist\n");
#endif
#ifdef CONFIG_ESP32S3_BLE
  ret = esp32s3_ble_initialize();
  printf("BLE: esp32s3_ble_initialize returned %d\n", ret);
  if (ret)
    printf("BLE: ERROR Failed to initialize BLE ret=%d\n", ret);
#endif
#ifdef CONFIG_ESP32S3_WIFI
  ret = board_wlan_init();
  if (ret < 0)
    syslog(LOG_ERR, "ERROR: Failed to initialize wireless subsystem=%d\n", ret);
#endif
#endif

#if defined(CONFIG_DEV_GPIO) && !defined(CONFIG_GPIO_LOWER_HALF)
  ret = esp32s3_gpio_init();
  if (ret < 0)
    syslog(LOG_ERR, "Failed to initialize GPIO Driver: %d\n", ret);
#endif

#ifdef CONFIG_ESP32S3_SDMMC
  ret = board_sdmmc_initialize();
  if (ret < 0)
    syslog(LOG_ERR, "ERROR: Failed to initialize SDMMC: %d\n", ret);
#endif

  /* ================================================================
   * v8.0: OV3660 Camera + DVP + GDMA bringup (ESP-IDF reference)
   * Sequence: bus_clk → reset → LCD_CLOCK → GPIO matrix → CAM_CTRL
   * ================================================================ */
  UNUSED(ret);
#ifdef CONFIG_OV3660
  {
    struct i2c_master_s *i2c;
    uint32_t sys_val;

    /* Step 1: Enable LCD_CAM bus clock (ESP-IDF: cam_ll_enable_bus_clock)
     * SYSTEM.perip_clk_en1 @ ESP32S3_PERIP_CLK_EN1, bit[8] = lcd_cam_clk_en */
    sys_val = getreg32(ESP32S3_PERIP_CLK_EN1);
    cam_debug("v8.0 PERIP_CLK_EN1 before=0x%08lX (bit8=%s)\n",
           sys_val, (sys_val & ESP32S3_LCD_CAM_CLK_EN) ? "ON" : "OFF");
    modifyreg32(ESP32S3_PERIP_CLK_EN1, 0, 1<<8);
    sys_val = getreg32(ESP32S3_PERIP_CLK_EN1);
    cam_debug("v8.0 PERIP_CLK_EN1 after =0x%08lX\n", sys_val);

    /* Step 2: Reset LCD_CAM module (ESP-IDF: cam_ll_reset_register)
     * SYSTEM.perip_rst_en1 @ ESP32S3_PERIP_RST_EN1, bit[8] = lcd_cam_rst */
    modifyreg32(ESP32S3_PERIP_RST_EN1, 0, 1<<8);
    up_udelay(10);
    modifyreg32(ESP32S3_PERIP_RST_EN1, 1<<8, 0);
    cam_debug("v8.0 LCD_CAM module reset done\n");

    /* Step 2b: Enable DMA bus clock (bit6 in PERIP_CLK_EN1)
     * and de-assert DMA reset (bit6 in PERIP_RST_EN1) */
    modifyreg32(ESP32S3_PERIP_CLK_EN1, 0, 1<<6);   /* DMA_CLK_EN */
    modifyreg32(ESP32S3_PERIP_RST_EN1, 1<<6, 0);   /* DMA_RST de-assert */
    cam_debug("v8.0 DMA bus clock enabled, reset de-asserted\n");

    /* Step 3: Configure LCD_CLOCK (base+0x00 @ 0x60041000)
     *   bit[31]    CLK_EN     = 1 (force enable register clock)
     *   bits[30:29] CLK_SEL    = 1 (XTAL=40MHz)
     *   bits[16:9]  CLKM_DIV_N = 0 (divider N)
     *   XCLK = XTAL / (N+1) = 40/1 = 40MHz (CAM_CTRL will divide further) */
    modifyreg32(0x60041000, 0, 0x80000000);   /* CLK_EN=1 */
    modifyreg32(0x60041000, 0x60000000, 0x20000000); /* CLK_SEL=1(XTAL) */
    cam_debug("v8.0 LCD_CLOCK=0x%08lX\n", getreg32(0x60041000));

    /* Step 4: Route XCLK via GPIO matrix (correct FUNC_OUT_SEL offset 0x554)
     * GPIO_FUNC10_OUT_SEL = GPIO_BASE(0x60004000) + 0x554 + 10*4 = 0x6000457C */
    esp32s3_gpio_matrix_out(XIAO_CAM_XCLK, 149, false, false);
    modifyreg32(IO_MUX_GPIO10, 0x00003FFF, 0x00000B00);  /* IO_MUX: GPIO, FUN_IE=1, drive=3 */
    cam_debug("v8.0 GPIO_MATRIX_OUT: XCLK GPIO%d signal=149 FUNC_OUT(0x%08lX)=0x%08lX IO_MUX=0x%08lX\n",
           XIAO_CAM_XCLK, (uint32_t)(0x60004554 + XIAO_CAM_XCLK*4),
           getreg32(0x60004554 + XIAO_CAM_XCLK*4), getreg32(IO_MUX_GPIO10));

    /* Step 5: Configure CAM_CTRL first WITHOUT update (base+0x04 @ ESP32S3_CAM_CTRL)
     *   bits[30:29] cam_clk_sel   = 2 (PLL240M=240MHz)
     *   bits[16:9]  cam_clkm_div_num = 11 (divider=11 → 240/12=20MHz)
     *   bit[8]      cam_vs_eof_en = 1
     *   bit[4]      cam_update    = 0 (NO UPDATE YET — latch after CTRL1+RGB) */
    putreg32((2<<29) | (11<<9) | ESP32S3_LCD_CAM_CLK_EN, ESP32S3_CAM_CTRL);
    cam_debug("v8.0 CAM_CTRL=0x%08lX\n", getreg32(ESP32S3_CAM_CTRL));

    /* Step 6: Configure CAM_CTRL1 (base+0x08 @ ESP32S3_CAM_CTRL1)
     *   bit[28]     cam_vh_de_mode_en = 0 (VSYNC+DE mode, simpler)
     *   bits[15:0]  cam_rec_data_bytelen = 0xFFFF (65535 = max, VSYNC controls EOF) */
    putreg32(0x0000FFFF, ESP32S3_CAM_CTRL1);
    putreg32(0x20800FFB, ESP32S3_CAM_RGB_YUV);         /* CAM_RGB_YUV: bypass=1, 8-bit mode */

    /* Step 7: Route DVP input signals to LCD_CAM */
    esp32s3_gpio_matrix_in(XIAO_CAM_D2, 133, false);
    esp32s3_gpio_matrix_in(XIAO_CAM_D3, 134, false);
    esp32s3_gpio_matrix_in(XIAO_CAM_D4, 135, false);
    esp32s3_gpio_matrix_in(XIAO_CAM_D5, 136, false);
    esp32s3_gpio_matrix_in(XIAO_CAM_D6, 137, false);
    esp32s3_gpio_matrix_in(XIAO_CAM_D7, 138, false);
    esp32s3_gpio_matrix_in(XIAO_CAM_D8, 139, false);
    esp32s3_gpio_matrix_in(XIAO_CAM_D9, 140, false);
    esp32s3_gpio_matrix_in(XIAO_CAM_VSYNC, 152, false);
    esp32s3_gpio_matrix_in(XIAO_CAM_HSYNC, 150, false);  /* HREF→CAM_H_ENABLE=150 (DE mode) */
    esp32s3_gpio_matrix_in(XIAO_CAM_PCLK, 149, false);  /* PCLK→CAM_PCLK=149 */

    /* Step 8: Quick XCLK sanity check */
    { int h = 0; for (int i = 0; i < 1000; i++) { if (getreg32(GPIO_IN_REG) & (1<<10)) h++; }
      cam_debug("v8.0 XCLK_GPIO10: %d/1000\n", h); }

    /* Step 9: GDMA configuration */
    putreg32(~0, GDMA_IN_INT_CLR_CH2); putreg32(0xFF, GDMA_IN_INT_ENA_CH2);  /* enable all DMA ints */
    putreg32(0, GDMA_IN_CONF0_CH2);
    modifyreg32(GDMA_IN_CONF0_CH2, 0, 1<<0); modifyreg32(GDMA_IN_CONF0_CH2, 1<<0, 0);
    putreg32(5, GDMA_IN_PERI_SEL_CH2);
    putreg32(0x0C, 0x6003F184);

    /* Step 10: I2C init + sensor init */
    i2c = esp32s3_i2cbus_initialize(0);
    if (i2c) {
      puts("v8.0 CAM_INIT");
      ret = ov3660_initialize(i2c);
      if (ret == 0) {
        puts("v8.0 INIT OK - starting stream start_streaming with SAME i2c handle");
        int sr = ov3660_start_streaming(i2c);
        cam_debug("v8.0 STREAM ret=%d\n", sr);
      } else {
        cam_debug("v8.0 INIT FAILED ret=%d\n", ret);
      }
      /* DMA init now handles descriptor chain in camera_dma.c */
      puts("v8.0 CAM+SENSOR OK - starting DMA");

      /* v2.5: DMA data-plane init */
      ret = esp32s3_camera_dma_init();
      if (ret == 0) {
        puts("v8.0 DMA INIT OK");
        usleep(500000);  /* sleep instead of mdelay — feeds WDT */
        esp32s3_camera_dma_invalidate();
        esp32s3_camera_dma_status();
      } else {
        cam_debug("v8.0 DMA INIT FAIL: %d\n", ret);
      }
    }
  }
#endif

  puts("DIAG: pre-TFLM init");
  /* Phase 3+4: TFLM init + Inference Task (mqueue-decoupled) */
  {
    extern const unsigned char g_model_data[];
    extern const unsigned int g_model_data_len;
    puts("TFLM: initializing MobileFaceNet...");
    int tflm_ret = tflm_init(g_model_data, g_model_data_len);
    if (tflm_ret == 0) {
      puts("TFLM: MobileFaceNet init OK");

      /* Start inference worker thread with message queues */
      if (inference_task_init() == 0) {
        puts("INFER: task started (2-stage: face_filter + MobileFaceNet)");

        /* Pre-WiFi: submit one frame for initial embedding */
        esp32s3_camera_dma_invalidate();
        const uint8_t *pre_buf = esp32s3_camera_dma_get_buffer();
        if (pre_buf && face_region_filter(pre_buf)) {
          inference_submit_frame(pre_buf);
          usleep(2000000);  /* wait up to 2s for inference */
          float emb[128];
          if (inference_get_result(emb)) {
            printf("FACE: emb[0]=%.4f\n", emb[0]);
            memcpy(emb_buf[0], emb, 128 * sizeof(float));
            g_tflm_ready = 1;
            puts("FACE: embedding captured");
          } else {
            puts("FACE: no face in pre-WiFi frame");
          }
        } else {
          puts("FACE: pre-WiFi frame skipped (no face detected)");
        }

        /* DIAG: forced inference — submit frame regardless to verify pipeline */
        {
          esp32s3_camera_dma_invalidate();
          const uint8_t *diag_buf = esp32s3_camera_dma_get_buffer();
          if (diag_buf) {
            puts("DIAG: forcing inference (bypass face filter)...");
            inference_submit_frame(diag_buf);
            usleep(2500000);
            float emb[128];
            if (inference_get_result(emb)) {
              printf("DIAG: emb[0]=%.4f emb[1]=%.4f emb[2]=%.4f emb[127]=%.4f\n",
                     emb[0], emb[1], emb[2], emb[127]);
              puts("DIAG: forced inference OK");
            } else {
              puts("DIAG: forced inference NO RESULT");
            }
          }
        }
      } else {
        puts("INFER: task init FAILED");
      }
    } else {
      printf("TFLM: init failed (ret=%d)\n", tflm_ret);
    }
  }

#ifdef CONFIG_ESP32S3_WIFI
  usleep(3000000);
  puts("NET: Starting WiFi/MQTT...");
  int net_ret = network_init();
  if (net_ret == 0) {
    puts("NET: Online");

    /* Publish stored pre-WiFi embeddings via MQTT */
    if (g_tflm_ready > 0) {
      printf("FACE: publishing %d stored embeddings via MQTT...\n", g_tflm_ready);
      for (int i = 0; i < g_tflm_ready; i++) {
        network_send_embedding(emb_buf[i], 128);
        usleep(500000);
      }
      puts("FACE: MQTT publish complete");
    }

  /* BLE scanner after WiFi+MQTT is up */
#ifdef CONFIG_ESP32S3_BLE
  puts("BLE: starting scan (10s)...");
  ble_scanner_run(10);
#endif

    /* Silhouette capture */
    puts("SIL: init silhouette extractor...");
    silhouette_extractor_init(160, 120);  /* QQVGA full frame */
    up_mdelay(200);

    /* Warm-up frame */
    {
      esp32s3_camera_dma_invalidate();
      uint8_t *buf = esp32s3_camera_dma_get_buffer();
      silhouette_extractor_process(buf);
      puts("SIL: warm-up done");
    }

    /* Capture loop: 5 frames, publish on motion */
    for (int fc = 0; fc < 5; fc++) {
      up_mdelay(300);
      esp32s3_camera_dma_invalidate();
      uint8_t *buf = esp32s3_camera_dma_get_buffer();
      bool motion = silhouette_extractor_process(buf);
      uint16_t rle_cnt = silhouette_get_rle_count();
      uint16_t fg_px  = silhouette_get_motion_pixels();

      printf("SIL: frame=%d motion=%d thresh=%u fg_px=%u rle=%u\n",
             fc, motion,
             silhouette_get_threshold(), fg_px, rle_cnt);

      if (motion && rle_cnt > 0 && rle_cnt != 0xFFFF) {
        int sr = network_send_silhouette(
          silhouette_get_rle(), rle_cnt,
          silhouette_get_width(), silhouette_get_height(),
          silhouette_get_threshold(), fg_px);
        printf("SIL: MQTT publish ret=%d (%u bytes)\n",
               sr, rle_cnt * 2);

        /* Two-stage face detection: if silhouette sees motion,
         * submit frame to inference task for face embedding */
        inference_submit_frame(buf);
      }

      /* Poll for any completed inference results */
      {
        float emb[128];
        if (inference_get_result(emb)) {
          printf("FACE: result emb[0]=%.4f\n", emb[0]);
          network_send_embedding(emb, 128);
        }
      }
    }
    puts("SIL: capture test done");

  } else {
    printf("NET: Init failed (ret=%d) — camera still functional\n", net_ret);
  }
#endif

  return OK;
}



