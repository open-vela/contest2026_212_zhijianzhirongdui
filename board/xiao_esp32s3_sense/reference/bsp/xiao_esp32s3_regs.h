/* XIAO ESP32S3 Sense — Shared Register Macros
 * Replaces magic numbers in bringup.c and camera_dma.c.
 * Located in board include/ so all board sources can find it.
 */
#ifndef __XIAO_ESP32S3_REGS_H
#define __XIAO_ESP32S3_REGS_H

/* ---- Register access macros ---- */
#define putreg32(v,a)     (*(volatile uint32_t *)(a) = (v))
#define getreg32(a)       (*(volatile uint32_t *)(a))
#define modifyreg32(a,c,s) (*(volatile uint32_t *)(a) = ((*(volatile uint32_t *)(a)) & ~(c)) | (s))

/* ---- SYSTEM registers ---- */
#define ESP32S3_PERIP_CLK_EN1     0x600C001C
#define ESP32S3_PERIP_RST_EN1     0x600C0024
#define ESP32S3_LCD_CAM_CLK_EN    (1 << 8)
#define ESP32S3_DMA_CLK_EN        (1 << 6)

/* ---- LCD_CAM registers ---- */
#define ESP32S3_LCD_CAM_BASE      0x60041000
#define ESP32S3_LCD_CLOCK         (ESP32S3_LCD_CAM_BASE + 0x00)
#define ESP32S3_CAM_CTRL          (ESP32S3_LCD_CAM_BASE + 0x04)
#define ESP32S3_CAM_CTRL1         (ESP32S3_LCD_CAM_BASE + 0x08)
#define ESP32S3_CAM_RGB_YUV       (ESP32S3_LCD_CAM_BASE + 0x0C)

/* CAM_CTRL bits */
#define CAM_CLK_SEL_PLL240M       (2 << 29)
#define CAM_VS_EOF_EN             (1 << 8)
#define CAM_UPDATE                (1 << 4)

/* CAM_CTRL1 bits */
#define CAM_START                 (1 << 29)

/* ---- GDMA registers ---- */
#define GDMA_BASE                 0x6003F000
#define GDMA_IN_CONF0_CH2         (GDMA_BASE + 0x180)
#define GDMA_IN_INT_ENA_CH2       (GDMA_BASE + 0x190)
#define GDMA_IN_INT_CLR_CH2       (GDMA_BASE + 0x194)
#define GDMA_IN_INT_ST_CH2        (GDMA_BASE + 0x18C)
#define GDMA_IN_LINK_CH2          (GDMA_BASE + 0x1A0)
#define GDMA_IN_PERI_SEL_CH2      (GDMA_BASE + 0x1C8)

/* ---- GPIO ---- */
#define GPIO_IN_REG               0x6000403C
#define IO_MUX_GPIO10             0x6000902C
#define GPIO_FUNC_OUT_SEL(n)      (0x60004554 + (n) * 4)

/* ---- Signal routing indices ---- */
#define SIG_CAM_PCLK              149
#define SIG_CAM_H_ENABLE           150
#define SIG_CAM_V_SYNC             152
#define SIG_CAM_DATA_IN0           133

/* ---- DMA descriptor ---- */
#define DMA_DESC_SIZE_MASK        0xFFF
#define DMA_DESC_OWNER_DMA        (1 << 31)

/* ---- Debug ---- */
#ifdef CONFIG_DEBUG_CAMERA
#  define cam_debug printf
#else
#  define cam_debug(...) do {} while(0)
#endif

#endif
