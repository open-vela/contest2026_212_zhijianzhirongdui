# xiao_esp32s3_sense — XIAO ESP32S3 Sense 板级适配

枢络 VelaMesh 边缘从节点的板级适配形态，经 manifest linkfile 映射到 openvela
工作树 `vendor/openvela/boards/contest2026_212_xiao_esp32s3_sense`，是本作品
「新硬件平台适配」得分项的载体。

## 硬件

Seeed Studio XIAO ESP32S3 Sense：ESP32-S3R8（双核 Xtensa LX7、8MB PSRAM/
8MB Flash）+ 扩展板 OV2640 摄像头（可换装 OV3660 模组）。

摄像头引脚（DVP 8-bit，见 `reference/bsp/xiao-esp32s3-sense.h`）：

| 信号 | GPIO | 信号 | GPIO |
|---|---|---|---|
| XCLK | 10 | PCLK | 13 |
| VSYNC | 38 | HREF | 47 |
| SIOD (SCCB) | 40 | SIOC (SCCB) | 39 |
| D0–D7 | 15/17/18/16/14/12/11/48 | PWDN/RESET | 未使用 |

## 目录

```text
xiao_esp32s3_sense/
├── CMakeLists.txt          # 板级构建入口（跟随 ARCH_BOARD 符号）
├── Kconfig                 # ARCH_BOARD_CONTEST2026_212_XIAO_ESP32S3_SENSE
├── configs/nsh/defconfig   # 从实测工作树移植的 vendor defconfig（WiFi/视频/OV3660/PSRAM）
├── src/
│   ├── CMakeLists.txt      # Stage 1 仅编译 boot stub
│   └── board_boot.c        # openvela_board_initialize 占位
└── reference/              # 移植自原工程的真实板级源码（本阶段不参与编译）
    ├── bsp/                # appinit / boot / bringup / 板头 / 寄存器 / MQTT 网络
    └── camera/             # OV2640/OV3660 DMA 采集、bringup 演进版本
```

## 当前状态（Stage 1 基线）

- 板级构建链路（CMake/Kconfig + linkfile）以 boot stub 打通，保证整仓可配置；
- `configs/nsh/defconfig` 为在真实 XIAO ESP32S3 Sense 上验证过的厂商配置
  （`CONFIG_ARCH_CHIP_ESP32S3WROOM1N8R8`、OCT PSRAM、WiFi、`CONFIG_DRIVERS_VIDEO`、
  `CONFIG_OV3660`、VIDEO_FB、WAPI 等）；
- `reference/` 内是团队在原 openvela 工作树上开发的 BSP 与摄像头 DMA 源码，
  保留原始 include 路径与演进版本，由后续板级 bring-up 任务纳入板级库编译；
- OV2640/OV3660 camera DMA 适配要点与实测诊断结论见
  [`CAMERA_DMA.md`](./CAMERA_DMA.md)（Arduino 基准对照、GDMA 描述符/LCD_CAM
  寄存器要点、遗留疑点与下一步验证）。

## 配置目标

在 openvela 中以本板为目标时使用：

```text
CONFIG_ARCH_BOARD_CONTEST2026_212_XIAO_ESP32S3_SENSE=y
```

> 注：移植的 defconfig 中 `CONFIG_ARCH_BOARD` 仍为上游板名 `esp32s3-eye`，
> 切换到本队板名符号的 defconfig 整改随后续 bring-up 任务完成（见
> CAMERA_DMA.md「后续工作」）。
