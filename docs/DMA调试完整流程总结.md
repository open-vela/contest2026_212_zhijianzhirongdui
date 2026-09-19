# OV3660 DMA 帧捕获调试流程总结

> 仅记录实际执行过的操作和观察到的结果。假设性结论均标注来源。

---

## 一、调试起点

**初始状态**（v2.0）：
- openvela 运行于 XIAO ESP32S3 Sense
- OV3660 传感器驱动 ov3660.c 已编写（248行，I2C初始化）
- PID=0x3660 验证通过，硬件链路确认
- XCLK 20MHz 通过 LCD_CAM 外设生成（Arduino dump 验证寄存器值 0x60001008）
- DVP 14引脚 GPIO Matrix 配置完成
- GDMA Channel2 绑定 LCD_CAM（peri_sel=5）
- 每次启动输出 `v18 OV3660_IFDEF` + `NO`（表示 DMA 缓冲区为空）

**初始配置值**：
- `CAM_CTRL` (0x60041004) = 0x60001008
- `CAM_CTRL1` (0x60041008) = `(4095 << 0) | (1 << 23)` = 0x00800FFF，后续设 bit29 = 0x20800FFF
- GDMA 描述符顺序：`dma_desc[0]=cam_buf地址, dma_desc[1]=0x1FFF, dma_desc[2]=0`
- GDMA 描述符地址写入 `IN_DSCR` (0x6003F1A0)，而非 `IN_LINK` (0x6003F190)
- `ov3660_start_streaming()` 写入精简寄存器集（约20个寄存器），格式设为 YUV422（0x4300=0x30, 0x501F=0x00）

---

## 二、Arduino 环境验证（基准线建立）

### 实验 1：Arduino 帧捕获
**操作**：编写 `xiao_ov3660_frame_capture.ino`，使用 esp32-camera 库初始化 OV3660，配置 JPEG QVGA，捕获5帧。
**观察**：5/5 帧捕获成功，JPEG 头验证通过（0xFF 0xD8），帧大小约 4.3KB。
**结论**：硬件（XIAO Sense、OV3660、PSRAM、PCB）完全正常。

### 实验 2：Arduino 寄存器 dump
**操作**：同一 sketch 中 dump LCD_CAM、GDMA、SYSTEM、GPIO Matrix 寄存器。
**观察**：
| 寄存器 | Arduino 值 |
|--------|-----------|
| CAM_CTRL (0x60041004) | 0x60001008 |
| CAM_CTRL1 (0x60041008) | 0x20800FFB |
| CAM_RGB_YUV (0x6004100C) | 0x00000000 |
| CAM_ENTRY_NUM (0x60041018) | 0x000000D6 |
| CAM_INT_ENA (0x60041020) | 0x00000000 |
| CAM_CLK_EN (0x6004102C) | 0x00000000 |
| LCD_CAM[0x00] (0x60041000) | 0x00000843 |
| GDMA_IN_CONF0_CH2 (0x6003F180) | 0x00000000 |
| GDMA_IN_CONF1_CH2 (0x6003F184) | 0x0000000C |
| GDMA_IN_PERI_SEL_CH2 (0x6003F1C8) | 0x0000003F |

**关键差异发现**：openvela 的 CAM_CTRL1 = 0x20800FFF，Arduino = 0x20800FFB。
- 0xFFF vs 0xFFB：差在 bit2。0xFFB = bit2=0（8-bit data width），0xFFF = bit2=1（16-bit）。

### 实验 3：Arduino Sensor 寄存器全量 dump（v2 sketch）
**操作**：编写 `xiao_ov3660_full_dump.ino`，在帧捕获成功后 dump OV3660 全部可读寄存器（300+个）。
**观察**：获得了 Arduino 工作状态下的字节精确传感器配置表。关键发现：
- SC_CTRL0 (0x3031) = 0x00（未使能 sync 输出——此为空闲状态值）
- SC_CTRL3 (0x3034) = 0x1A
- CLK_CTRL00 (0x3400) = 0x04
- FORMAT_CTRL00 (0x4300) = 0x30（非 JPEG 模式——此为后捕获空闲状态）
- ISP_FORMAT_MUX (0x501F) = 0x00

---

## 三、openvela 端代码修复（按时间顺序）

### 修复 1：CAM_CTRL1 值修正 (v2.1)
**操作**：将 bringup.c 中 CAM_CTRL1 写入从 `(4095<<0)|(1<<23)` + bit29 设置，改为直接写 `0x20800FFB`。
**同时**：补全 LCD_CAM_CLK 寄存器 `0x60041000 = 0x00000843`。
**删除**：无效的 bit30/bit31 翻转操作。
**观察**：构建 677KB，烧录后仍输出 `NO`。

### 修复 2：GDMA 启动寄存器修正 (v2.2 → v2.3)
**操作**：查阅 ESP-IDF 源码 `gdma_ll.h` 和 `gdma_struct.h`，发现：
- `IN_DSCR` (0x6003F1A0) 字段 `dscr_addr` 为**只读**状态寄存器（当前正在处理的描述符地址）
- `IN_LINK` (0x6003F190) 字段 `addr` (bits[19:0]) = 描述符地址，`start` (bit22) = 启动位
- 原代码将描述符地址写入 `IN_DSCR`（无效操作），应写入 `IN_LINK` 并设 start 位

**修改**：将 `putreg32(((uint32_t)dma_desc) & 0xFFFFF, 0x6003F1A0)` 改为 `putreg32((((uint32_t)dma_desc) & 0xFFFFF) | (1 << 22), 0x6003F190)`
**观察**：构建成功，烧录后输出 `NO`。同时发现串口输出丢失——USB serial 在 `--after hard_reset` 后未恢复（需物理重新插拔 USB 恢复）。

### 修复 3：DMA 描述符字顺序修正 (v2.4)
**操作**：查阅 ESP-IDF `dma_types.h`，确认 GDMA 描述符内存布局：
```c
typedef struct dma_descriptor_s {
    struct { uint32_t size:12; uint32_t length:12; ... uint32_t owner:1; } dw0;  // Word 0
    void *buffer;                                                                 // Word 1
    struct dma_descriptor_s *next;                                                // Word 2
} dma_descriptor_t;
```
原代码：`dma_desc[0]=cam_buf, dma_desc[1]=0x1FFF` — **顺序反了**。
- dw0 (offset 0) 应是控制字（size/length/owner），但被填入了 buffer 地址
- buffer 地址的高位 bit31=0，被 GDMA 解读为 owner=0 → DMA 不拥有此描述符

**修改**：
```c
dma_desc[0] = 4095 | (4095 << 12) | (1 << 31);  // dw0: size=4095, length=4095, owner=1
dma_desc[1] = (uint32_t)cam_buf;                  // buffer pointer
dma_desc[2] = 0;                                   // next=NULL
```
**观察**：构建成功，烧录后输出 `NO`。

### 修复 4：OV3660 流启动寄存器补全 (v2.3 → v3.4)
**操作**：基于 Arduino sensor dump 逐步修正 ov3660.c：

a) **寄存器地址 typo 修正**：`0x380`→`0x3800`, `0x381`→`0x3812`, `0x430`→`0x4300`

b) **JPEG 输出格式**：原 init 表设 `0x4300=0x30`(YUV)，`0x501F=0x00`(YUV422)。streaming 中增补 `0x4300=0xE1`(JPEG)、`0x4301=0x01`、`0x501F=0x03`(JPEG ISP输出)

c) **Sync 输出使能**：原代码写 `SC_CTRL0 (0x3031)=0x1A`。Arduino dump 显示空闲态 SC_CTRL0=0x00，SC_CTRL3(0x3034)=0x1A。尝试改写 SC_CTRL3=0x1A（v3.2），后又改回 SC_CTRL0=0x1A（v3.4）。结果均 `NO`。

d) **Arduino 参考值对齐**：修正 init 表中多个寄存器匹配 Arduino dump：
- `0x3820`: 0x40→0x01, `0x3821`: 0x00→0x21
- `0x460B`: 0x35→0x37, `0x4837`: 0x16→0x00
- `0x5000`: 0x06→0xA7, `0x5001`: 0x01→0xA3
- 补全 `0x3033`-`0x3037`、`0x5601`-`0x5602`、`0x3400`=0x04

### 修复 5：Arduino 字节精确 init 表替换 (v4.0)
**操作**：用 Arduino `xiao_ov3660_full_dump.ino` dump 的 300+个寄存器完整替换 ov3660.c 的 `g_ov3660_init_regs[]` 表，确保初始化后的传感器状态与 Arduino 工作环境字节一致。
**构建**：ov3660.c 膨胀至 620行，nuttx.bin 从 677KB 增至 742KB。
**观察**：烧录后仍输出 `NO`。

### 辅助调试：串口消失问题
**现象**（v2.2→v2.3之间首次出现，后续反复出现）：esptool `--after hard_reset` 后 picocom 无任何输出，但 esptool `chip_id` 能正常连接芯片。
**定位**：发现 `~/picocom_loop.sh` 后台自动重连占用 `/dev/ttyACM0`，导致端口被锁。
**解决**：`kill -9` picocom_loop 进程后，esptool chip_id 触发硬复位，再打开 picocom 能正常收到 NSH 输出。

---

## 四、已验证的正确配置（当前 v4.0 状态）

以下配置经 Arduino dump 对比验证，与 Arduino 工作环境一致：

| 组件 | 配置项 | 值 | 验证来源 |
|------|--------|-----|----------|
| CAM | CAM_CTRL | 0x60001008 | Arduino dump |
| CAM | CAM_CTRL1 | 0x20800FFB | Arduino dump |
| CAM | LCD_CAM_CLK | 0x00000843 | Arduino dump |
| CAM | CAM_START | bit21 of CAM_CTRL | ESP32-S3 TRM |
| GDMA | 描述符格式 | dw0=[0], buffer=[1], next=[2] | ESP-IDF dma_types.h |
| GDMA | 描述符内容 | size=32767, length=32767, owner=1 (bit31) | ESP-IDF descriptor spec |
| GDMA | 启动方式 | IN_LINK (0x6003F190) bit22=start | ESP-IDF gdma_ll.h |
| GDMA | PERI_SEL | 5 (LCD_CAM) | ESP-IDF gdma_ll.h |
| OV3660 | Init 表 | 300+寄存器 = Arduino dump | Arduino 寄存器 dump |
| 系统 | PERIP_CLK_EN1 | bit6(DMA)+bit8(LCD_CAM)=1 | Arduino dump |
| 内存 | cam_buf | 32KB PSRAM (.ext_ram段) | — |

---

## 五、未解决的观察

### 观察 1：CAM_INT_ST 始终为 0
**实验**（v2.2 诊断输出）：在 CAM_START 后延迟 500ms 读取 `LCD_CAM_CAM_INT_ST` (0x60041028)，值恒为 `0x00000000`。该寄存器 bit0=VSYNC中断标志。值为 0 表示 LCD_CAM 模块从未检测到 VSYNC 信号边沿。

### 观察 2：ov3660_start_streaming 返回 OK
**实验**（v3.6 中加入返回值检查）：`ov3660_start_streaming()` 返回 0，无 "stream FAIL" 输出。说明 I2C 写入全部成功（无 NACK）。

### 观察 3：GDMA_STATE 恒为 IDLE
**实验**（v2.2 诊断输出）：`GDMA_IN_STATE_CH2` (0x6003F194) 值为 0（IDLE 状态）。结合 CAM_INT_ST=0，表明 DMA 从未被触发——因为上游 LCD_CAM 从未产生 DMA 请求。

### 观察 4：OV3660 sensor 寄存器在 Arduino 环境中与 openvela 完全一致（v4.0）
**实验**（v4.0 全量替换）：将 openvela 的 init 表完全替换为 Arduino dump 的字节精确值后，openvela 端仍然 NO。

---

## 六、假设（未经验证，标注实验依据）

**假设 H1**（产生于观察 4 之后）：**XCLK 未实际到达 OV3660 传感器。**

依据：
- v4.0 的 sensor 寄存器值与 Arduino 完全一致，但 Arduino 环境下 PCLK/VSYNC 正常输出，openvela 环境下 CAM_INT_ST 始终为 0
- openvela 通过 LCD_CAM 外设 + gpio_matrix_out(GPIO10, 149) 生成 XCLK
- 实验 2 的 Arduino GPIO Matrix dump 显示 GPIO10 IO_MUX = 0x00000A00，但未验证 openvela 端的 GPIO10 IO_MUX 寄存器值
- **如果传感器没有时钟输入，无论寄存器如何配置，都无法产生像素数据输出**

**验证方法**：用示波器测量 GPIO10 是否有 20MHz 方波。若无示波器，可用另一块 ESP32 做 GPIO 频率计数。

**假设 H2**（产生于实验 2 的 GPIO Matrix 对比）：**GPIO Matrix 信号路由在 openvela 和 Arduino 之间存在差异。**

依据：
- Arduino dump 中所有 camera 引脚的 `FUNC_IN_SEL` 均为 0x00000000，IO_MUX 各不相同（0x00000A00, 0x00001A00, 0x00004F00 等）
- openvela 使用 `gpio_matrix_in(pin, signal_idx, false)` 配置输入路由，该函数同时设置 FUNC_IN_SEL 和 IO_MUX
- 但 IO_MUX 的值在 openvela 端未被验证是否与 Arduino 一致

**验证方法**：在 openvela 固件中添加 IO_MUX 寄存器 dump，对比 Arduino 值。

**假设 H3**（产生于观察 1、2、3）：**OV3660 在 openvela 环境下处于"寄存器已配置但硬件未激活"状态。**

依据：
- I2C 寄存器写入成功（H2 排除）
- sensor 寄存器值匹配 Arduino（H4 排除）
- 但 CAM_INT_ST=0，说明传感器未输出 VSYNC
- Arduino 环境中，esp_camera_init() 内部有多个步骤：sensor_init → set_pixformat → set_framesize → cam_config，其中 cam_config 可能包含除 I2C 寄存器配置之外的额外硬件操作（如 GPIO 上电、外部复位引脚控制等）

**验证方法**：对比 openvela 与 Arduino 在 PWDN/RESET 引脚（GPIO -1/-1，即未使用）和传感器上电时序上的差异。

---

## 七、构建统计

| 版本 | 修改 | 结果 |
|------|------|:--:|
| v2.0 | 原始代码 | NO |
| v2.1 | CAM_CTRL1=0x20800FFB | NO |
| v2.2 | IN_LINK start | NO |
| v2.3 | ov3660 streaming JPEG/sync | NO |
| v2.4 | DMA描述符顺序修正 | NO |
| v2.5 | 清理诊断代码 | NO |
| v2.6 | 跳过 GDMA 启动 | NO（串口消失）|
| v2.7 | 完全移除摄像头代码 | NO（串口消失）|
| v2.8 | 恢复 v2.0 | NO（串口消失）|
| v2.9 | 完全回退 ov3660.c | NO（串口消失）|
| v3.0 | 全部修复合并 | NO |
| v3.1 | init表 JPEG格式 | NO |
| v3.2 | SC_CTRL3 替换 SC_CTRL0 | NO |
| v3.3 | 全SC_CTRL寄存器 Arduino参考 | NO |
| v3.4 | SC_CTRL0 恢复 + COMP_CTRL | NO |
| v3.5 | streaming 返回值检查 | NO（确认返回OK）|
| v3.6 | CAM_BLK 入口诊断 | NO（确认进入执行）|
| v3.7 | streaming 合并到 init | NO |
| v3.8 | 32KB PSRAM buffer | NO |
| v4.0 | Arduino 300+寄存器全量替换 | NO |

累计构建次数：27 次（含重新构建）；串口消失恢复次数：3 次（均通过 USB 重新插拔恢复）。
