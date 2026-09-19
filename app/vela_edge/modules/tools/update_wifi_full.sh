#!/bin/bash
# ═══════════════════════════════════════════════════════════════
# ESP32-S3 家庭网络 WiFi 更新 + 编译 + 烧录 + 串口验证
# 在 VM (openvela@192.168.25.131) 上运行此脚本
# ═══════════════════════════════════════════════════════════════

NUTTX="/home/openvela/openvela-project/nuttx"
BOARD_SRC="$NUTTX/boards/xtensa/esp32s3/xiao-esp32s3-sense/src"
ESPTOOL="/home/openvela/openvela-project/myenv/bin/esptool.py"

cd $NUTTX

echo "=== 1. 更新 WiFi 配置 ==="
sed -i 's|CONFIG_NETINIT_WAPI_SSID=".*"|CONFIG_NETINIT_WAPI_SSID="Family804"|' .config
sed -i 's|CONFIG_NETINIT_WAPI_PASSPHRASE=".*"|CONFIG_NETINIT_WAPI_PASSPHRASE="11223344"|' .config
sed -i 's|#define WIFI_SSID.*|#define WIFI_SSID         "Family804"|' $BOARD_SRC/xiaosense_network.c
sed -i 's|#define WIFI_PASSPHRASE.*|#define WIFI_PASSPHRASE   "11223344"|' $BOARD_SRC/xiaosense_network.c
sed -i 's|#define MQTT_BROKER.*|#define MQTT_BROKER       "192.168.31.194"|' $BOARD_SRC/xiaosense_network.c
grep -E 'WAPI_SSID|WAPI_PASSPHRASE' .config
grep -E 'WIFI_SSID|WIFI_PASSPHRASE|MQTT_BROKER' $BOARD_SRC/xiaosense_network.c | head -3

echo "=== 2. 修复编译链接 ==="
rm -f arch/xtensa/src/board include/arch/board include/arch/chip drivers/platform 2>/dev/null
find . -name '.depend' -delete 2>/dev/null
ln -sf boards/xtensa/esp32s3/common arch/xtensa/src/board
mkdir -p include/arch && ln -sf ../../boards/xtensa/esp32s3/xiao-esp32s3-sense/include include/arch/board
ln -sf ../arch/xtensa/include/esp32s3 include/arch/chip
mkdir -p drivers && ln -sf ../drivers/dummy drivers/platform
cd boards/xtensa/esp32s3/common && rm -f board src include 2>/dev/null
ln -sf ../xiao-esp32s3-sense/src board; ln -sf ../xiao-esp32s3-sense/src src; ln -sf ../xiao-esp32s3-sense/include include
cd $NUTTX && echo "Symlinks OK"

echo "=== 3. 编译 ==="
source /home/openvela/openvela-project/myenv/bin/activate
export PATH=/home/openvela/openvela-project/prebuilts/gcc/linux-x86_64/xtensa-esp32s3-elf/bin:$PATH
make -j4 EXTRAFLAGS="-Wno-cpp -Wno-deprecated-declarations"

echo "=== 4. 烧录 ==="
echo "123" | sudo -S $ESPTOOL --chip esp32s3 \
  --port /dev/ttyACM0 --baud 921600 --before default-reset --after hard-reset \
  write-flash -z --flash-mode dio --flash-freq 80m --flash-size 8MB 0x0 nuttx.bin

echo "=== 5. 读串口验证 ==="
timeout 35 head -c 8192 /dev/ttyACM0

echo "=== DONE ==="
