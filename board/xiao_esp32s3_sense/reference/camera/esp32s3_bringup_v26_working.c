/****************************************************************************
 * boards/xtensa/esp32s3/xiao-esp32s3-sense/src/esp32s3_bringup.c
 *
 * SPDX-License-Identifier: Apache-2.0
 * v2.6 - DIAG: no GDMA start, CAM+sensor only, clean minimal output
 * PSRAM: OCTAL (ESP32-S3R8), Camera SCCB: GPIO39/40, XCLK: LCD_CAM
 ****************************************************************************/

#define putreg32(v,a)     (*(volatile uint32_t *)(a) = (v))
#define getreg32(a)       (*(volatile uint32_t *)(a))
#define modifyreg32(a,c,s) (*(volatile uint32_t *)(a) = ((*(volatile uint32_t *)(a)) & ~(c)) | (s))

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

/****************************************************************************
 * Public Functions
 ****************************************************************************/

int esp32s3_bringup(void)
{
  int ret;

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
  /* GPIO39/40 diagnostic before I2C init */
  printf("I2C_PRE GPIO39=0x%08lX GPIO40=0x%08lX\n",
         getreg32(0x600090A0), getreg32(0x600090A4));

  ret = board_i2c_init();

  printf("I2C_POST ret=%d CTR=0x%08lX SR=0x%08lX\n",
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
  if (ret)
    syslog(LOG_ERR, "ERROR: Failed to initialize BLE\n");
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
   * V17: OV3660 Camera + DVP + GDMA bringup
   * ================================================================ */
  UNUSED(ret);
#ifdef CONFIG_OV3660
  {
    struct i2c_master_s *i2c;
    modifyreg32(0x600C001C, 0, 1<<8);
    modifyreg32(0x600C0024, 1<<8, 0);
    modifyreg32(0x600C001C, 0, 1<<6);
    modifyreg32(0x600C0024, 1<<6, 0);
    esp32s3_gpio_matrix_out(XIAO_CAM_XCLK, 149, false, false);
    putreg32(0x60001008, 0x60041004);
    up_mdelay(10);
    putreg32(0x00000843, 0x60041000);
    putreg32(0x20800FFB, 0x60041008);
    esp32s3_gpio_matrix_in(XIAO_CAM_D2, 133, false);
    esp32s3_gpio_matrix_in(XIAO_CAM_D3, 134, false);
    esp32s3_gpio_matrix_in(XIAO_CAM_D4, 135, false);
    esp32s3_gpio_matrix_in(XIAO_CAM_D5, 136, false);
    esp32s3_gpio_matrix_in(XIAO_CAM_D6, 137, false);
    esp32s3_gpio_matrix_in(XIAO_CAM_D7, 138, false);
    esp32s3_gpio_matrix_in(XIAO_CAM_D8, 139, false);
    esp32s3_gpio_matrix_in(XIAO_CAM_D9, 140, false);
    esp32s3_gpio_matrix_in(XIAO_CAM_VSYNC, 152, false);
    esp32s3_gpio_matrix_in(XIAO_CAM_HSYNC, 150, false);
    esp32s3_gpio_matrix_in(XIAO_CAM_PCLK, 149, false);
    putreg32(~0, 0x6003F194); putreg32(0, 0x6003F190);
    putreg32(0, 0x6003F180);
    modifyreg32(0x6003F180, 0, 1<<0); modifyreg32(0x6003F180, 1<<0, 0);
    putreg32(5, 0x6003F1C8);
    putreg32(0x0C, 0x6003F184);
    i2c = esp32s3_i2cbus_initialize(0);
    if (i2c) {
      static volatile uint32_t dma_desc[3] __attribute__((aligned(4)));
      static uint8_t __attribute__((aligned(4))) cam_buf[4096];
      puts("v2.6 NODMA");
      ret = ov3660_initialize(i2c);
      if (ret == 0) {
        i2c = esp32s3_i2cbus_initialize(0);
        if (i2c) ov3660_start_streaming(i2c);
      }
      /* GDMA descriptor: dw0[0]=control, [1]=buffer, [2]=next */
      dma_desc[0] = 4095 | (4095 << 12) | (1 << 31);
      dma_desc[1] = (uint32_t)cam_buf;
      dma_desc[2] = 0;
      /* v2.6: Skip GDMA start - just test sensor+cam init */
      puts("v2.6 CAM+SENSOR INIT OK - no DMA start");

      /* v2.5: DMA data-plane init (added to v2.6 working baseline) */
      ret = esp32s3_camera_dma_init();
      if (ret == 0) {
        puts("v2.5 DMA INIT OK");
        up_mdelay(500);
        esp32s3_camera_dma_invalidate();
        esp32s3_camera_dma_status();
      } else {
        printf("v2.5 DMA INIT FAIL: %d\n", ret);
      }
    }
  }
#endif
  return OK;
}
