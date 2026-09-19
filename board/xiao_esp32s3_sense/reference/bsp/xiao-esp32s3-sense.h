/****************************************************************************
 * boards/xtensa/esp32s3/xiao-esp32s3-sense/src/xiao-esp32s3-sense.h
 *
 * SPDX-License-Identifier: Apache-2.0
 *
 * Licensed to the Apache Software Foundation (ASF) under one or more
 * contributor license agreements.  See the NOTICE file distributed with
 * this work for additional information regarding copyright ownership.  The
 * ASF licenses this file to you under the Apache License, Version 2.0 (the
 * "License"); you may not use this file except in compliance with the
 * License.  You may obtain a copy of the License at
 *
 *   http://www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing, software
 * distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
 * WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.  See the
 * License for the specific language governing permissions and limitations
 * under the License.
 *
 ****************************************************************************/

#ifndef __BOARDS_XTENSA_ESP32S3_XIAO_ESP32S3_SENSE_SRC_XIAO_ESP32S3_SENSE_H
#define __BOARDS_XTENSA_ESP32S3_XIAO_ESP32S3_SENSE_SRC_XIAO_ESP32S3_SENSE_H

/****************************************************************************
 * Included Files
 ****************************************************************************/

#include <nuttx/config.h>
#include <nuttx/compiler.h>
#include <stdint.h>

/****************************************************************************
 * Pre-processor Definitions
 ****************************************************************************/

/* XIAO ESP32S3 Sense GPIOs ************************************************/

/* BOOT Button */

#define BUTTON_BOOT         0

/* User LED */

#define GPIO_LED            21

/* Camera DVP Pin Definitions **********************************************/

#define XIAO_CAM_XCLK       10   /* Camera master clock output */
#define XIAO_CAM_PCLK       13   /* Camera pixel clock */
#define XIAO_CAM_VSYNC      38   /* Camera vertical sync */
#define XIAO_CAM_HSYNC      47   /* Camera horizontal sync / HREF */
#define XIAO_CAM_SIOD       40   /* Camera I2C data (SCCB) */
#define XIAO_CAM_SIOC       39   /* Camera I2C clock (SCCB) */

/* Camera data pins D2-D9 (8-bit parallel) */

#define XIAO_CAM_D2         15   /* Y2 */
#define XIAO_CAM_D3         17   /* Y3 */
#define XIAO_CAM_D4         18   /* Y4 */
#define XIAO_CAM_D5         16   /* Y5 */
#define XIAO_CAM_D6         14   /* Y6 */
#define XIAO_CAM_D7         12   /* Y7 */
#define XIAO_CAM_D8         11   /* Y8 */
#define XIAO_CAM_D9         48   /* Y9 */

/* I2C Bus (shared with camera SCCB on GPIO39/40) ***************************/

#define XIAO_I2C_SDA        40
#define XIAO_I2C_SCL        39

/* SD Card (SPI mode) *******************************************************/

#define XIAO_SD_CS          3
#define XIAO_SD_SCK         7
#define XIAO_SD_MISO        8
#define XIAO_SD_MOSI        10   /* Note: shared with CAM_XCLK */

/* PDM Microphone **********************************************************/

#define XIAO_MIC_CLK        42
#define XIAO_MIC_DATA       41

/****************************************************************************
 * Public Types
 ****************************************************************************/

/****************************************************************************
 * Public Data
 ****************************************************************************/

#ifndef __ASSEMBLY__

/****************************************************************************
 * Public Function Prototypes
 ****************************************************************************/

/****************************************************************************
 * Name: esp32s3_bringup
 *
 * Description:
 *   Perform architecture-specific initialization
 *
 ****************************************************************************/

int esp32s3_bringup(void);

/****************************************************************************
 * Name: esp32s3_gpio_init
 *
 * Description:
 *   Configure the GPIO driver.
 *
 ****************************************************************************/

#ifdef CONFIG_DEV_GPIO
int esp32s3_gpio_init(void);
#endif

/****************************************************************************
 * Name: board_spiflash_init
 *
 * Description:
 *   Initialize the SPIFLASH and register the MTD device.
 *
 ****************************************************************************/

#ifdef CONFIG_ESP32S3_SPIFLASH
int board_spiflash_init(void);
#endif

/****************************************************************************
 * Name: board_i2c_init
 *
 * Description:
 *   Configure the I2C driver.
 *
 ****************************************************************************/

#ifdef CONFIG_I2C_DRIVER
int board_i2c_init(void);
#endif

#endif /* __ASSEMBLY__ */
#endif /* __BOARDS_XTENSA_ESP32S3_XIAO_ESP32S3_SENSE_SRC_XIAO_ESP32S3_SENSE_H */
