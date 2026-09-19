# SOP v2.0 — XIAO ESP32-S3 OpenVela 开发标准操作流程

> **重大变更（v2.0）**：VM 上已安装 Multica daemon，Agent 可直接操作编译环境。不再需要 SFTP 乒乓。

## 0. 环境速查

| 项目 | 值 |
|------|-----|
| VM SSH | `openvela@192.168.25.131`，密码 `123` |
| 工具链 | `source ~/openvela-project/myenv/bin/activate && export PATH=~/openvela-project/prebuilts/gcc/linux-x86_64/xtensa-esp32s3-elf/bin:$PATH` |
| NuttX 根目录 | `~/openvela-project/nuttx/` |
| 板级源码 | `boards/xtensa/esp32s3/xiao-esp32s3-sense/src/` |
| Multica CLI | `~/.local/bin/multica`（已在 PATH） |
| Daemon | `multica daemon status` 确认 running |

## 1. 开发工作流（新版）

### 方式 A：Agent 自动操作（推荐）

```
你在 Multica 里 @Agent → Agent SSH 进 VM → 改代码 → 编译 → 烧录 → 抓日志 → 回报
```

无需手动 SFTP、无需手动编译。

### 方式 B：手动操作（兜底）

```
1. SSH 进 VM
2. 直接编辑 ~/openvela-project/nuttx/ 下的源码
3. 编译 → 烧录 → 验证（见下方 2-5 节）
```

## 2. 编译

```bash
cd ~/openvela-project/nuttx
source ../myenv/bin/activate
export PATH=~/openvela-project/prebuilts/gcc/linux-x86_64/xtensa-esp32s3-elf/bin:~/openvela-project/myenv/bin:/usr/bin:/bin
rm -f nuttx
make -j4
# 成功标志: "Generated: nuttx.bin"
```

## 3. 镜像打包

```bash
# ELF → ESP32-S3 镜像（--ram-only-header 使 BLE init 返回 0）
esptool.py --chip esp32s3 elf2image --ram-only-header \
  -fs 8MB -fm dio -ff 40m -o nuttx_xxx.bin nuttx
```

## 4. 烧录

```bash
# 4.1 杀 picocom
echo 123 | sudo -S killall -9 picocom 2>/dev/null
sleep 1

# 4.2 烧录
esptool.py --chip esp32s3 --port /dev/ttyACM0 --baud 921600 \
  --before default-reset --after hard-reset write-flash -z \
  --flash-mode dio --flash-freq 40m --flash-size 8MB 0x0 nuttx_xxx.bin

# 4.3 抓串口日志
for i in 1 2 3 4 5 6 7; do
  timeout 25 cat /dev/ttyACM0 2>/dev/null
  sleep 2
done > /tmp/blog_xxx.log 2>&1 &

# 4.4 读日志（过滤噪点）
grep -v "invalid header" /tmp/blog_xxx.log
```

## 5. 备份

```bash
mkdir -p ~/openvela-project/backup/vX.Y_描述/{source,configs,binaries,tools}
# 拷贝所有修改过的源文件、.config、nuttx.bin
```

## 6. 关键配置

| 配置 | 值 | 说明 |
|------|-----|------|
| `CONFIG_LIBCXXTOOLCHAIN` | y | 使用工具链 C++ 库 |
| `CONFIG_TFLITEMICRO` | n | 用 standalone TFLite |
| `libtflitemicro.a` | 链接到 LDLIBS | 不用 --whole-archive（会崩 WiFi） |
| Arena | 2048*1024 | 2MB PSRAM |
| `--ram-only-header` | esptool elf2image | BLE 才能 init=0 |

## 7. 常见错误速查

| 症状 | 根因 | 修复 |
|------|------|------|
| `_U/_L/_N not declared` | NuttX ctype.h 宏污染 | nuttx_cxx_compat.h 移除 `#include <ctype.h>` |
| BLE init=-1 | 镜像缺少 --ram-only-header | 用 esptool 重新 elf2image |
| WiFi 关联后崩溃 | standalone TFLite 冲突 | libtflitemicro 放 LDLIBS，不用 --whole-archive |
| 烧录失败 "port busy" | picocom 占用端口 | `sudo killall -9 picocom` |
| 首次启动崩溃 | PSRAM 冷启动 | 等 35s 抓第二次启动 |
| `AllocateTensors FAILED` | arena < 2MB | arena=2048*1024 |
| `MicroPrintf undefined` | C++ 名字修饰不匹配 | micro_log.h 加 extern "C" |
| 推理 NO RESULT | 非阻塞单次查询 | inference_get_result 改轮询 |
| XCLK 无输出 | LCD_CLOCK 用 XTAL | 改为 PLL240M (CLK_SEL=2) |
