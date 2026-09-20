---
name: esp32s3-flash-pipeline
description: 构建、打包、烧录 openvela ESP32-S3 边缘节点固件，并采集首启与二次启动串口证据。用户提到烧录、刷机、flash ESP32-S3 或边缘节点固件时使用。
---

# ESP32-S3 烧录管线

## 何时使用

用户要求“烧录”“刷机”“flash ESP32-S3”“更新边缘节点固件”或排查烧录后启动异常时使用。
任何真实烧录都先让用户确认物理连接、目标串口与目标板，不能把干跑结果表述成实机成功。

## 前置条件

- 工程默认位于 `~/openvela-project/nuttx`；Python 虚拟环境位于 `~/openvela-project/myenv`。
- 工具链目录为 `~/openvela-project/prebuilts/gcc/linux-x86_64/xtensa-esp32s3-elf/bin`。
- 已安装 `esptool.py`、`make`、`timeout`，用户可访问目标串口。
- 当前配置应包含 `CONFIG_LIBCXXTOOLCHAIN=y`、`CONFIG_TFLITEMICRO=n`。
- 真实烧录具有破坏性：必须再次核对端口，且不得在用户未确认时执行。

## 标准流程

1. 运行 `scripts/flash.sh --build-only`。脚本激活 venv、加入工具链路径并执行 `make -j4`；
   成功后应看到构建系统的 `Generated: nuttx.bin`，脚本还会检查 `nuttx` ELF 是否存在。
2. 运行 `scripts/flash.sh --image-only` 生成镜像。命令必须保留
   `--ram-only-header -fs 8MB -fm dio -ff 40m`；缺少 `--ram-only-header` 会导致
   `BLE init=-1`。
3. 用户确认物理连接后运行 `scripts/flash.sh --port /dev/ttyACM0 --confirm-flash`。
   脚本先用 `killall -9 picocom` 释放端口，再以 921600 波特率、DIO/40 MHz/8 MB、
   地址 `0x0` 写入，并执行 hard reset。
4. 用 `scripts/serial_capture.sh --port /dev/ttyACM0 --output-dir ./serial-evidence`
   取证。默认抓两轮、每轮 25 秒，并在两轮之间等待 35 秒以覆盖首启崩溃后的第二次启动。
5. 核对 esptool 完成信息和串口日志中的应用启动、WiFi/BLE 初始化、节点状态上报；缺任一证据时
   只报告已完成的步骤，不宣称端到端成功。

## 参数示例

```sh
# 只构建
scripts/flash.sh --project-dir "$HOME/openvela-project/nuttx" --build-only

# 使用自定义产物名打包但不烧录
scripts/flash.sh --elf nuttx --image nuttx_x.bin --image-only

# 完整构建、打包与烧录（需要明确确认）
scripts/flash.sh --port /dev/ttyACM0 --confirm-flash
```

## 失败处理与速查

| 现象 | 检查与处理 |
|---|---|
| `BLE init=-1` | 重新检查镜像命令是否含 `--ram-only-header`；不要烧录普通 header 镜像。 |
| WiFi 关联时崩溃 | 将 `libtflitemicro` 放入 `LDLIBS`，不要对它使用 `--whole-archive`。 |
| `AllocateTensors FAILED` | 将 TFLM arena 设为 `2048*1024`，再检查剩余内存。 |
| 摄像头 XCLK 无输出 | 使用 PLL240M，设置 `CLK_SEL=2`。 |
| `MicroPrintf` undefined | 在 `micro_log.h` 的声明处补正确的 `extern "C"` 边界。 |
| C++ 链接异常 | 确认 `CONFIG_LIBCXXTOOLCHAIN=y`。 |
| 重复/冲突的 TFLM 构建 | 确认 `CONFIG_TFLITEMICRO=n`，使用项目显式链接的库。 |
| 串口 busy | 确认没有要保留的会话，再执行 `killall -9 picocom`；核对用户组和设备权限。 |
| 找不到串口或 ELF | 停止流程并报告确切路径；不得用干跑或旧日志替代本次实机结果。 |

