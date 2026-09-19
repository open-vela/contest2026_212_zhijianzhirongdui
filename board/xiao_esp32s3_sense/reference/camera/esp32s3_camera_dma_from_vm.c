/****************************************************************************
 * boards/xtensa/esp32s3/xiao-esp32s3-sense/src/esp32s3_camera_dma.c
 *
 * DMA data-plane for OV3660 camera on XIAO ESP32S3 Sense.
 * Based on evaluation report recommendations:
 *   1. GDMA descriptors MUST be in internal SRAM (0x3FC80000-0x3FD50000)
 *   2. Frame buffers in PSRAM with 64-byte cache-line alignment
 *   3. Explicit cache invalidation before CPU reads DMA-written data
 *
 * SPDX-License-Identifier: Apache-2.0
 ****************************************************************************/

#include <nuttx/config.h>
#include <stdio.h>
#include <string.h>
#include <debug.h>
#include <nuttx/arch.h>
#include "esp32s3_gpio.h"
#include "hardware/esp32s3_gpio_sigmap.h"

/* ---- Register offset definitions (ESP32-S3 TRM) ----------------------- */
/* LCD_CAM  base: 0x60041000 */
#define CAM_CTRL_REG          0x60041000
#define CAM_CTRL1_REG         0x60041004
#define CAM_RGB_YUV_REG       0x60041008
#define CAM_CLK_REG           0x60041000   /* same as CTRL for clock bits */

/* GDMA base: 0x6003F000 */
#define GDMA_MISC_CONF_REG    0x6003F064
#define GDMA_IN_CONF0_CH0     0x6003F100
#define GDMA_IN_PERI_SEL_CH0  0x6003F108
#define GDMA_IN_INT_CLR_CH0   0x6003F114
#define GDMA_IN_INT_ST_CH0    0x6003F118
#define GDMA_IN_INT_RAW_CH0   0x6003F11C
#define GDMA_IN_LINK_CH0      0x6003F128  /* addr[19:0]+start bit[22] */

/* ---- Register access macros ------------------------------------------- */

#define putreg32(v,a)       (*(volatile uint32_t *)(a) = (v))
#define getreg32(a)         (*(volatile uint32_t *)(a))
#define modifyreg32(a,c,s)  (*(volatile uint32_t *)(a) = ((*(volatile uint32_t *)(a)) & ~(c)) | (s))

/* ---- GDMA descriptor (12 bytes, must be in internal SRAM) ------------ */

typedef struct {
    struct {
        uint32_t size       : 12;
        uint32_t length     : 12;
        uint32_t reserved   : 6;
        uint32_t suc_eof    : 1;
        uint32_t owner      : 1;
    } dw0;
    void    *buffer;
    struct dma_descriptor_s *next;
} dma_descriptor_t;

#define DMA_OWNER_CPU  0
#define DMA_OWNER_DMA  1

#define CAM_REC_LEN     4094   /* Must match V20: cam_rec_data_bytelen */
#define DESC_BUF_SIZE   4095   /* GDMA descriptor size (12-bit field) */

/* ---- Internal SRAM validation ----------------------------------------- */
/* ESP32-S3 internal SRAM: 0x3FC80000 - 0x3FD4FFFF */

static int is_internal_sram(uintptr_t addr)
{
    return (addr >= 0x3FC80000 && addr <= 0x3FD4FFFF);
}

/* ---- DMA state --------------------------------------------------------- */

#define DESC_BUF_SIZE   4096   /* Must be <= 4095 (12-bit GDMA descriptor field) */

/* Descriptor: static = internal SRAM (guaranteed by C data section) */
static dma_descriptor_t g_dma_desc __attribute__((aligned(4)));

/* Frame buffer: static = internal SRAM, small for first test */
static uint8_t g_cam_buf[DESC_BUF_SIZE] __attribute__((aligned(64)));

/****************************************************************************
 * Public Functions
 ****************************************************************************/

/****************************************************************************
 * Name: esp32s3_camera_dma_init
 *
 * Description:
 *   Configure LCD_CAM peripheral for DVP reception and set up GDMA channel.
 *   Returns 0 on success, negative errno on failure.
 *
 *   Step-by-step:
 *   1. Enable LCD_CAM + GDMA clocks, release reset
 *   2. Configure DVP pins via GPIO matrix (PCLK=13, VSYNC=38, HREF=47,
 *      D2-D9=15,17,18,16,14,12,11,48)
 *   3. Configure LCD_CAM clock and control registers
 *   4. Allocate frame buffer in PSRAM (64-byte aligned)
 *   5. Configure GDMA descriptor + link
 *   6. Report status
 ****************************************************************************/

int esp32s3_camera_dma_init(void)
{
    uintptr_t desc_addr;
    int ret = 0;

    /* --- 1. Enable LCD_CAM + GDMA clocks via CLK_EN1 / RST_EN1 --- */
    /* HAL-verified: PERIPH_LCD_CAM_MODULE & PERIPH_GDMA_MODULE use
     * SYSTEM_PERIP_CLK_EN1_REG (0x600C001C) and RST_EN1_REG (0x600C0024) */

    modifyreg32(0x600C001C, 0, (1 << 8) | (1 << 6));  /* CLK_EN1: LCD_CAM+GDMA */
    modifyreg32(0x600C0024, (1 << 8) | (1 << 6), 0);  /* RST_EN1: release */

    up_udelay(100);

    /* --- 1b. IO_MUX direct connection for DVP high-speed signals --- */
    /* DVP requires IO_MUX to bypass the slower GPIO matrix.
     * Register: 0x60009000 + (GPIO + 1) * 4
     * MCU_SEL[14:12]=0=default(bypass), FUN_IE=1(on inputs), FUN_PU=1(on clks) */

#define IOOMUX(g) (0x60009000 + ((g) + 1) * 4)

    /* XCLK (GPIO10): output, no IE, no PU (driven by LEDC) */
    putreg32(0x00000000, IOOMUX(10));

    /* PCLK (GPIO13): input, IE=1, PU=1, DRV=1 */
    putreg32(0x00001A00, IOOMUX(13));

    /* VSYNC (GPIO38): input, IE=1, DRV=3 */
    putreg32(0x00004F00, IOOMUX(38));

    /* HREF (GPIO47): input, IE=1, PU=1 */
    putreg32(0x00000A80, IOOMUX(47));

    /* DVP Data D2-D9: input, IE=1, PU=1, DRV=1 */
    putreg32(0x00001A00, IOOMUX(15));  /* D2/Y2 */
    putreg32(0x00001A00, IOOMUX(17));  /* D3/Y3 */
    putreg32(0x00001A00, IOOMUX(18));  /* D4/Y4 */
    putreg32(0x00001A00, IOOMUX(16));  /* D5/Y5 */
    putreg32(0x00001A00, IOOMUX(14));  /* D6/Y6 */
    putreg32(0x00001A00, IOOMUX(12));  /* D7/Y7 */
    putreg32(0x00001A00, IOOMUX(11));  /* D8/Y8 */
    putreg32(0x00001A00, IOOMUX(48));  /* D9/Y9 */

#undef IOOMUX

    /* --- 2a. XCLK via LEDC (Arduino uses LEDC, NOT LCD_CAM clock!) --- */
    /* LEDC_HS_TIMER0: 40MHz XTAL, 1/2 divider → 20MHz
     * LEDC_HS_CH0: duty 50%, route to GPIO10 via GPIO matrix */
    {
        /* Enable LEDC clock (CLK_EN1 bit 10 = LEDC_CLK_EN) */
        modifyreg32(0x600C001C, 0, 1 << 10);

        /* LEDC_HSTIMER0_CONF (0x600190A0): clk_src=1(XTAL_40M), div=2, duty_res=1,
         * timer_en=1 */
        putreg32((1 << 1) | (2 << 8) | (1 << 13) | (1 << 17) | (1 << 25), 0x600190A0);

        /* LEDC_HSCH0_CONF0 (0x60019008): timer_sel=0, idle_lv=0, sig_out_en=1 */
        putreg32(1 << 2, 0x60019008);

        /* LEDC_HSCH0_HPOINT (0x6001900C): hpoint = 1 (50% duty with div=2) */
        putreg32(1, 0x6001900C);

        /* LEDC_HSCH0_DUTY (0x60019010): duty = 1 */
        putreg32(1, 0x60019010);

        /* Route LEDC_HS_SIG_OUT0 (index 103) to GPIO10 */
        esp32s3_gpio_matrix_out(10, 103, false, false);
    }

    /* --- 2b. DVP pins via GPIO matrix --- */
    /* Pin mapping matches xiao-esp32s3-sense.h and Arduino camera_pins.h:
     * PCLK=13(in), VSYNC=38(in), HREF=47(in)
     * D2=15, D3=17, D4=18, D5=16, D6=14, D7=12, D8=11, D9=48 */

    esp32s3_gpio_matrix_in(13, 141, false);  /* PCLK → CAM_PCLK (141) */
    esp32s3_gpio_matrix_in(38, 152, false);  /* VSYNC → CAM_V_SYNC (152) */
    esp32s3_gpio_matrix_in(47, 150, false);  /* HREF → CAM_H_REF (150) */

    /* Data D2-D9 → CAM_DATA_0-7 (133-140) */
    esp32s3_gpio_matrix_in(15, 133, false);  /* D2/Y2 → CAM_DATA0 */
    esp32s3_gpio_matrix_in(17, 134, false);  /* D3/Y3 → CAM_DATA1 */
    esp32s3_gpio_matrix_in(18, 135, false);  /* D4/Y4 → CAM_DATA2 */
    esp32s3_gpio_matrix_in(16, 136, false);  /* D5/Y5 → CAM_DATA3 */
    esp32s3_gpio_matrix_in(14, 137, false);  /* D6/Y6 → CAM_DATA4 */
    esp32s3_gpio_matrix_in(12, 138, false);  /* D7/Y7 → CAM_DATA5 */
    esp32s3_gpio_matrix_in(11, 139, false);  /* D8/Y8 → CAM_DATA6 */
    esp32s3_gpio_matrix_in(48, 140, false);  /* D9/Y9 → CAM_DATA7 */

    /* --- 3. LCD_CAM camera control --- */

    /* Reset CAM (bit 30) and AFIFO (bit 31) — HAL-verified bit positions */
    modifyreg32(CAM_CTRL1_REG, 0, (1 << 30) | (1 << 31));
    up_udelay(10);
    modifyreg32(CAM_CTRL1_REG, (1 << 30) | (1 << 31), 0);

    /* CAM_CTRL (HAL-verified bit positions):
     *   bit[31]:    clk_en = 1
     *   bits[30:29]: clk_sel = 1 (PLL_160M)
     *   bits[16:9]:  clkm_div_num = 8 (160/8 = 20MHz)
     *   bit[8]:      cam_vs_eof_en = 1
     *   bit[4]:      cam_update = 1 */
    putreg32((1 << 31) | (1 << 29) | (8 << 9) | (1 << 8) | (1 << 4), CAM_CTRL_REG);

    /* CAM_CTRL1 (HAL-verified bit positions):
     *   bits[15:0]:  cam_rec_data_bytelen = 4094
     *   bit[23]:     cam_vsync_filter_en = 1
     *   bit[28]:     cam_vh_de_mode_en = 1
     *   bit[29]:     cam_start (set later via modifyreg) */
    putreg32(4094 | (1 << 23) | (1 << 28), CAM_CTRL1_REG);

    /* CAM_RGB_YUV: default (RGB565) = 0 */
    putreg32(0, CAM_RGB_YUV_REG);

    /* --- 5. Frame buffer: static in internal SRAM, 64-byte aligned --- */
    printf("DMA: cam_buf=0x%08lX size=%d\n",
           (uint32_t)g_cam_buf, DESC_BUF_SIZE);
    memset(g_cam_buf, 0, DESC_BUF_SIZE);

    /* --- 6. GDMA descriptor (MUST be in internal SRAM) --- */
    desc_addr = (uintptr_t)&g_dma_desc;
    if (!is_internal_sram(desc_addr)) {
        printf("DMA: FATAL - descriptor at 0x%08lX not in SRAM!\n",
               (uint32_t)desc_addr);
        return -2;
    }
    printf("DMA: descriptor=0x%08lX (SRAM verified)\n", (uint32_t)desc_addr);

    memset(&g_dma_desc, 0, sizeof(g_dma_desc));
    g_dma_desc.dw0.size   = DESC_BUF_SIZE;
    g_dma_desc.dw0.length = DESC_BUF_SIZE;
    g_dma_desc.dw0.suc_eof = 1;
    g_dma_desc.dw0.owner  = DMA_OWNER_DMA;
    g_dma_desc.buffer     = g_cam_buf;
    g_dma_desc.next       = NULL;

    /* --- 7. GDMA Channel 0 RX setup (peripheral 5 = LCD_CAM) --- */
    /* MISC_CONF: bit 1 = clk_en */
    modifyreg32(GDMA_MISC_CONF_REG, 0, (1 << 1));

    /* IN_CONF0: bit 0 = in_rst, bit 2 = in_data_burst_en,
     * bit 3 = indscr_burst_en */
    modifyreg32(GDMA_IN_CONF0_CH0, 0, 1 << 0);   /* reset */
    modifyreg32(GDMA_IN_CONF0_CH0, 1 << 0, 0);    /* release reset */
    modifyreg32(GDMA_IN_CONF0_CH0, 0, (1 << 2) | (1 << 3)); /* burst en */

    /* PERI_SEL: select LCD_CAM (peripheral ID 5) */
    putreg32(5, GDMA_IN_PERI_SEL_CH0);

    /* Clear interrupts */
    putreg32(0x3FF, GDMA_IN_INT_CLR_CH0);

    /* Link descriptor: write low 20 bits of SRAM address + start bit (22)
     * to GDMA_IN_LINK_CH0 (0x6003F128). Do NOT write to 0x6003F130
     * (that's the read-only dscr_addr register). */
    {
        uint32_t link_val = ((uint32_t)&g_dma_desc) & 0x000FFFFF;
        link_val |= (1 << 22);  /* INLINK_START */
        putreg32(link_val, GDMA_IN_LINK_CH0);
    }

    /* --- 8. Re-trigger cam_update then start capture --- */
    /* cam_update (bit 4 of CAM_CTRL) latches all three CAM registers.
     * Must be set AFTER all CAM_CTRL1/CAM_RGB_YUV writes, or they
     * won't take effect. Hardware auto-clears this bit. */
    modifyreg32(CAM_CTRL_REG, 0, 1 << 4);  /* latch all CAM regs */

    /* Start capture: cam_start (bit 29 of CAM_CTRL1) */
    modifyreg32(CAM_CTRL1_REG, 0, 1 << 29);

    /* Trigger update again to latch cam_start */
    modifyreg32(CAM_CTRL_REG, 0, 1 << 4);

    printf("DMA: INIT complete. CAM_CTRL=0x%08lX CAM_CTRL1=0x%08lX\n",
           getreg32(CAM_CTRL_REG), getreg32(CAM_CTRL1_REG));
    printf("DMA: GDMA_INT_ST=0x%08lX GDMA_LINK=0x%08lX\n",
           getreg32(GDMA_IN_INT_ST_CH0), getreg32(GDMA_IN_LINK_CH0));

    return 0;
}

/****************************************************************************
 * Name: esp32s3_camera_dma_status
 *
 * Description:
 *   Print DMA and camera status for diagnostic purposes.
 ****************************************************************************/

void esp32s3_camera_dma_status(void)
{
    uint32_t cam_ctrl   = getreg32(CAM_CTRL_REG);
    uint32_t cam_ctrl1  = getreg32(CAM_CTRL1_REG);
    uint32_t int_st     = getreg32(GDMA_IN_INT_ST_CH0);
    uint32_t int_raw    = getreg32(GDMA_IN_INT_RAW_CH0);
    uint32_t link       = getreg32(GDMA_IN_LINK_CH0);
    uint32_t desc_addr  = (uint32_t)&g_dma_desc;

    printf("DMA_STAT: CAM_CTRL=0x%08lX CAM_CTRL1=0x%08lX\n",
           cam_ctrl, cam_ctrl1);
    printf("DMA_STAT: INT_ST=0x%08lX INT_RAW=0x%08lX LINK=0x%08lX\n",
           int_st, int_raw, link);
    printf("DMA_STAT: DESC=0x%08lX BUF=0x%08lX size=%d\n",
           desc_addr, (uint32_t)g_cam_buf, DESC_BUF_SIZE);
    printf("DMA_STAT: BUF[0..7]=%02X%02X%02X%02X %02X%02X%02X%02X\n",
           g_cam_buf[0], g_cam_buf[1], g_cam_buf[2], g_cam_buf[3],
           g_cam_buf[4], g_cam_buf[5], g_cam_buf[6], g_cam_buf[7]);

    /* GPIO input diagnostic: check if DVP sync signals are toggling */
    {
        uint32_t in0 = getreg32(0x60004038);  /* GPIO_IN_REG  (GPIO 0-31) */
        uint32_t in1 = getreg32(0x6000403C);  /* GPIO_IN1_REG (GPIO 32-53) */
        int pclk    = (in0 >> 13) & 1;  /* GPIO13 = PCLK */
        int vsync   = (in1 >> (38 - 32)) & 1;  /* GPIO38 = VSYNC */
        int href    = (in1 >> (47 - 32)) & 1;  /* GPIO47 = HREF */
        printf("DMA_STAT: GPIO_IN0=0x%08lX IN1=0x%08lX PCLK=%d VSYNC=%d HREF=%d\n",
               in0, in1, pclk, vsync, href);

        /* Verify GPIO10 is outputting XCLK */
        {
            uint32_t out0 = getreg32(0x60004004);  /* GPIO_OUT_REG (0-31) */
            uint32_t en0  = getreg32(0x60004020);  /* GPIO_ENABLE_REG (0-31) */
            int xclk_out = (out0 >> 10) & 1;
            int xclk_en  = (en0 >> 10) & 1;
            uint32_t out_sel10 = getreg32(0x60004554 + 10 * 4); /* FUNC10_OUT_SEL */
            printf("DMA_STAT: GPIO10 OUT=%d EN=%d OUT_SEL=0x%08lX EN_REG=0x%08lX\n",
                   xclk_out, xclk_en, out_sel10, en0);

            /* Quick PCLK toggle check: sample 1000 times, count highs */
            {
                int i, highs = 0;
                for (i = 0; i < 1000; i++) {
                    if (getreg32(0x60004038) & (1 << 13)) highs++;
                }
                printf("DMA_STAT: PCLK toggle highs=%d/1000 (0=dead, ~500=toggling)\n", highs);
            }
        }
    }
}

/****************************************************************************
 * Name: esp32s3_camera_dma_invalidate
 *
 * Description:
 *   Invalidate CPU cache for the frame buffer after DMA writes.
 *   Must be called before CPU reads the buffer.
 ****************************************************************************/

void esp32s3_camera_dma_invalidate(void)
{
    /* Cache invalidation: force CPU to re-read from PSRAM */
    up_invalidate_dcache((uintptr_t)g_cam_buf,
                         (uintptr_t)(g_cam_buf + DESC_BUF_SIZE));
}

/****************************************************************************
 * Name: esp32s3_camera_dma_get_buffer
 *
 * Description:
 *   Return pointer to the current frame buffer.
 ****************************************************************************/

uint8_t *esp32s3_camera_dma_get_buffer(void)
{
    return g_cam_buf;
}
