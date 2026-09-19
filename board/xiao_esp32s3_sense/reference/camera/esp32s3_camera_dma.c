/****************************************************************************
 * boards/xtensa/esp32s3/xiao-esp32s3-sense/src/esp32s3_camera_dma.c
 * v8.0 — Chained DMA: 8 descriptors × 4KB = 32KB frame buffer
 ****************************************************************************/

#include <nuttx/config.h>
#include <stdio.h>
#include <string.h>
#include <debug.h>
#include <nuttx/arch.h>
#include "esp32s3_gpio.h"
#include "hardware/esp32s3_gpio_sigmap.h"

#define DESC_BUF_SIZE  2048        /* per-descriptor buffer size */
#define NUM_DESCS      16           /* chained descriptors chained descriptors */
#define TOTAL_BUF_SIZE (DESC_BUF_SIZE * NUM_DESCS)  /* 32KB */

/* Flat uint32_t descriptor: [0]=dw0, [1]=buffer, [2]=next */
static volatile uint32_t g_dma_desc[NUM_DESCS][3] __attribute__((aligned(4)));
static uint8_t g_cam_buf[TOTAL_BUF_SIZE] __attribute__((aligned(64)));

#include "xiao_esp32s3_regs.h"

int esp32s3_camera_dma_init(void)
{
    memset((void*)g_cam_buf, 0, TOTAL_BUF_SIZE);
    memset((void*)g_dma_desc, 0, sizeof(g_dma_desc));

    /* Build chained descriptors */
    for (int i = 0; i < NUM_DESCS; i++)
    {
        uint32_t *desc = (uint32_t*)g_dma_desc[i];

        /* dw0: size=4KB-1, length=0 (filled by DMA), owner=1(DMA), suc_eof=0 */
        desc[0] = ((DESC_BUF_SIZE - 1) & 0xFFF)
                | (0 << 30)   /* suc_eof = 0 */
                | (1 << 31);  /* owner = DMA */

        /* dw1: buffer pointer */
        desc[1] = (uint32_t)(g_cam_buf + i * DESC_BUF_SIZE);

        /* dw2: next descriptor (NULL for last) */
        if (i < NUM_DESCS - 1)
            desc[2] = (uint32_t)g_dma_desc[i + 1];
        else
            desc[2] = 0;
    }

    cam_debug("DMA: %d descs chain, buf=0x%08lX total=%d DW0[0]=0x%08lX\n",
           NUM_DESCS, (uint32_t)g_cam_buf, TOTAL_BUF_SIZE, g_dma_desc[0][0]);

    /* Start GDMA link with first descriptor */
    {
        uint32_t link_val = ((uint32_t)g_dma_desc[0]) & 0x000FFFFF;
        link_val |= (1 << 22);  /* INLINK_START */
        putreg32(link_val, GDMA_IN_LINK_CH2);  /* GDMA_IN_LINK_CH2 */
    }

    /* Force CAM_CTRL vs_eof+update, then cam_start */
    modifyreg32(ESP32S3_CAM_CTRL, 0, ESP32S3_LCD_CAM_CLK_EN | (1<<4));
    modifyreg32(ESP32S3_CAM_CTRL1, 0, 1 << 29);

    cam_debug("DMA: BEFORE_START CAM_CTRL=0x%08lX CAM_CTRL1=0x%08lX\n",
           getreg32(ESP32S3_CAM_CTRL), getreg32(ESP32S3_CAM_CTRL1));

    return 0;
}

void esp32s3_camera_dma_status(void)
{
    uint32_t cam_ctrl   = getreg32(ESP32S3_CAM_CTRL);
    uint32_t cam_ctrl1  = getreg32(ESP32S3_CAM_CTRL1);
    uint32_t int_st     = getreg32(0x6003F18C);  /* DMA_IN_INT_ST_CH2 */
    uint32_t link       = getreg32(GDMA_IN_LINK_CH2);

    cam_debug("DMA_STAT: CAM_CTRL=0x%08lX CAM_CTRL1=0x%08lX INT_ST=0x%08lX\n",
           cam_ctrl, cam_ctrl1, int_st);

    /* Dump each descriptor's DW0 to see which ones were filled */
    int filled_bytes = 0;
    for (int i = 0; i < NUM_DESCS; i++)
    {
        uint32_t dw0 = g_dma_desc[i][0];
        int owner = (dw0 >> 31) & 1;
        int length = (dw0 >> 12) & 0xFFF;
        filled_bytes += length & 0xFFF;
        cam_debug("DMA_STAT: DESC[%d] DW0=0x%08lX owner=%d len=%d buf=0x%08lX\n",
               i, dw0, owner, length, g_dma_desc[i][1]);
    }

    cam_debug("DMA_STAT: TOTAL filled=%d bytes\n", filled_bytes);
    cam_debug("DMA_STAT: BUF[0..15]=%02X%02X%02X%02X %02X%02X%02X%02X %02X%02X%02X%02X %02X%02X%02X%02X\n",
           g_cam_buf[0], g_cam_buf[1], g_cam_buf[2], g_cam_buf[3],
           g_cam_buf[4], g_cam_buf[5], g_cam_buf[6], g_cam_buf[7],
           g_cam_buf[8], g_cam_buf[9], g_cam_buf[10], g_cam_buf[11],
           g_cam_buf[12], g_cam_buf[13], g_cam_buf[14], g_cam_buf[15]);

    /* Quick XCLK sanity */
    { int h = 0; for (int i = 0; i < 1000; i++) {
        if (getreg32(GPIO_IN_REG) & (1 << 10)) h++; }
      cam_debug("DMA_STAT: XCLK=%d/1000 PCLK=", h);
      h = 0; for (int i = 0; i < 1000; i++) {
        if (getreg32(GPIO_IN_REG) & (1 << 13)) h++; }
      printf("%d/1000\n", h); }
}

void esp32s3_camera_dma_invalidate(void)
{
    up_invalidate_dcache((uintptr_t)g_cam_buf,
                         (uintptr_t)(g_cam_buf + TOTAL_BUF_SIZE));
}

uint8_t *esp32s3_camera_dma_get_buffer(void)
{
    return g_cam_buf;
}
