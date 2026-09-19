# OV2640 / OV3660 Camera DMA 适配要点（XIAO ESP32S3 Sense）

本文件从团队实测调试记录（`DMA调试完整流程总结.md`）与系统级诊断报告
（《OpenVela 移植至 Seeed Studio XIAO ESP32S3 Sense：摄像头 DMA 异常诊断与
系统级可行性深度评估报告》）提炼，供后续板级 bring-up 任务直接引用。原始源码见
`reference/camera/` 与 `reference/bsp/`。

## 1. 硬件基线（已验证）

- XIAO ESP32S3 Sense（ESP32-S3R8，N16R8 / 板载 OCT PSRAM），扩展板 DVP 摄像头。
- OV2640 与 OV3660（SCCB 地址 0x3C，PID 读出 `0x3660` 验证通过）均在同一引脚上
  通过 Arduino `esp32-camera` 完成 5/5 帧 JPEG 捕获 —— **硬件链路无故障**，
  问题完全在 openvela 侧软件配置。
- DVP 引脚矩阵：XCLK=GPIO10、PCLK=GPIO13、VSYNC=GPIO38、HREF=GPIO47、
  SIOD=GPIO40、SIOC=GPIO39、D0–D7 = GPIO15/17/18/16/14/12/11/48；
  PWDN/RESET 未使用。

## 2. 已验证正确的关键寄存器值

用 Arduino 固件字节级 dump 建立基准，openvela 侧必须对齐：

| 组件 | 寄存器 | 正确值 | 说明 |
|---|---|---|---|
| LCD_CAM | `CAM_CTRL` (0x60041004) | `0x60001008` | XCLK 经 GPIO Matrix 输出 |
| LCD_CAM | `CAM_CTRL1` (0x60041008) | `0x20800FFB` | 低 12 位为窗口宽度；**bit2=0 → 8-bit 位宽**（误写 0xFFF 会变成 16-bit） |
| LCD_CAM | `CAM_CLK` (0x60041000) | `0x00000843` | 时钟使能 |
| GDMA | 描述符布局 | word0=控制字, word1=buffer, word2=next | **顺序不能反**，否则 buffer 地址高位被解释成 owner=0，DMA 不接管 |
| GDMA | 描述符控制字 | `size/length=4095(或32767), owner=bit31` | owner=1 表示 DMA 持有 |
| GDMA | 启动 | 写 `IN_LINK` (0x6003F190)：低 20 位描述符地址 + bit22 start | `IN_DSCR` (0x6003F1A0) 是只读当前描述符状态，不是启动口 |
| GDMA | `IN_PERI_SEL_CH2` (0x6003F1C8) | `5` | Channel2 外设选择 = LCD_CAM |
| 时钟 | PERIP_CLK_EN1 | bit6(DMA)+bit8(LCD_CAM)=1 | 外设门控必须开 |
| DMA 缓冲 | cam_buf | 32KB，位于 PSRAM `.ext_ram` 段 | 帧缓冲不能落内部 BSS |

## 3. 必须实施的四件事（系统级路径）

1. **重写引脚矩阵映射**：openvela BSP 预设引脚与 XIAO Sense 扩展板不一致，
   DVP 14 根信号线全部按上表经 GPIO Matrix 重映射；XCLK 走
   `gpio_matrix_out(GPIO10, SIGNALn, ...)`，并核对 IO_MUX 寄存器与
   Arduino dump 一致。
2. **物理内存分级**：DMA 描述符放在**内部 RAM**（DMA 可访问且天然 coherent），
   帧缓冲放 PSRAM；避免全局 BSS 重定位选项把描述符搬到 PSRAM。
3. **显式缓存同步**：GDMA 写 PSRAM 后、CPU 读帧前 `esp_cache_msync()`
   （或对应 cache writeback/invalidate 调用），否则拿到的是陈旧 cache 行。
4. **defconfig 工程级修正**（参考 `configs/nsh/defconfig`）：
   `CONFIG_DRIVERS_VIDEO=y`、`CONFIG_VIDEO_FB=y`、OV3660 驱动、
   PSRAM OCT 80MHz、`CONFIG_ESP32S3_SPIRAM=y`/`SPIRAM_MODE_OCT`，
   并关掉导致描述符错位分配的 BSS 重定位选项。

## 4. 实测现象与遗留疑点（后续 bring-up 的排查起点）

- 传感器 I2C 写全部成功（start_streaming 返回 0），init 表与 Arduino
  字节一致，但 `CAM_INT_ST` (0x60041028) 恒为 0、`GDMA_IN_STATE_CH2`
  (0x6003F194) 恒为 IDLE —— LCD_CAM 从未收到 VSYNC，即 **DMA 未被上游触发**。
- 首要假设 H1：**XCLK 未真正到达 OV3660**。寄存器配置一致但传感器无像素输出，
  下一步应用示波器/第二块 ESP32 频率计数确认 GPIO10 上存在 20MHz 方波，
  并 dump openvela 端 GPIO10 IO_MUX 对比 Arduino 的 `0x00000A00`。
- 次要假设：Arduino `esp_camera_init()` 在寄存器表之外还有 PWDN/上电时序等
  硬件动作，openvela bring-up 需要补齐等价时序。
- 调试副作用记录：esptool `--after hard_reset` 后 USB-serial 可能消失，
  需物理重插；调试时先确认没有后台 picocom 占用 `/dev/ttyACM*`。

## 5. reference/ 文件索引

- `reference/camera/esp32s3_camera_dma.c` / `_from_vm.c` —— DMA 采集驱动两版实现；
- `reference/camera/ov3660_from_vm.c` —— OV3660 寄存器表/流式启动（300+ 寄存器 Arduino 对齐版）；
- `reference/camera/bringup_v26_base.c`、`esp32s3_bringup_from_vm.c`、
  `esp32s3_bringup_v26_working.c` —— bringup 演进版本；
- `reference/bsp/esp32s3_{appinit,boot,bringup}.c`、`xiao-esp32s3-sense.h`、
  `xiao_esp32s3_regs.h` —— 板初始化、引脚/寄存器定义；
- `reference/bsp/xiaosense_network.c` —— 板侧 WiFi/MQTT 上行（边缘节点链路层）。

## 6. 后续工作

1. 将 `reference/` 源码纳入板级库编译（当前 `src/CMakeLists.txt` 仅编译 stub）；
2. defconfig 的 `CONFIG_ARCH_BOARD` 从上游 `esp32s3-eye` 切换为本队板符号
   `contest2026_212_xiao_esp32s3_sense`，补齐 Kconfig 板目录注册；
3. 按第 3、4 节完成 DMA 四条整改与 XCLK 实测；
4. OV2640 默认配置回归（QVGA/JPEG），OV3660 作为高分辨率步态/人脸输入。
