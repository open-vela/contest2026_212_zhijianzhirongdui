#!/bin/bash
# Run this on the VM (openvela@192.168.25.131) to update WiFi + rebuild + flash
NUTTX="/home/openvela/openvela-project/nuttx"
BOARD_SRC="$NUTTX/boards/xtensa/esp32s3/xiao-esp32s3-sense/src"

cd $NUTTX

# 1. Update WiFi credentials
sed -i 's|CONFIG_NETINIT_WAPI_SSID=".*"|CONFIG_NETINIT_WAPI_SSID="Family804"|' .config
sed -i 's|CONFIG_NETINIT_WAPI_PASSPHRASE=".*"|CONFIG_NETINIT_WAPI_PASSPHRASE="11223344"|' .config

# 2. Update C code
sed -i 's|#define WIFI_SSID.*|#define WIFI_SSID         "Family804"|' $BOARD_SRC/xiaosense_network.c
sed -i 's|#define WIFI_PASSPHRASE.*|#define WIFI_PASSPHRASE   "11223344"|' $BOARD_SRC/xiaosense_network.c
sed -i 's|#define MQTT_BROKER.*|#define MQTT_BROKER       "192.168.31.194"|' $BOARD_SRC/xiaosense_network.c

echo "=== Verify changes ==="
grep -E 'WAPI_SSID|WAPI_PASSPHRASE' .config
grep -E 'WIFI_SSID|WIFI_PASSPHRASE|MQTT_BROKER' $BOARD_SRC/xiaosense_network.c | head -3

# 3. Fix symlinks
rm -f arch/xtensa/src/board include/arch/board include/arch/chip drivers/platform 2>/dev/null
find . -name '.depend' -delete 2>/dev/null
ln -sf boards/xtensa/esp32s3/common arch/xtensa/src/board
mkdir -p include/arch && ln -sf ../../boards/xtensa/esp32s3/xiao-esp32s3-sense/include include/arch/board
ln -sf ../arch/xtensa/include/esp32s3 include/arch/chip
mkdir -p drivers && ln -sf ../drivers/dummy drivers/platform
cd boards/xtensa/esp32s3/common && rm -f board src include 2>/dev/null
ln -sf ../xiao-esp32s3-sense/src board
ln -sf ../xiao-esp32s3-sense/src src
ln -sf ../xiao-esp32s3-sense/include include
cd $NUTTX

# 4. Build
source /home/openvela/openvela-project/myenv/bin/activate
export PATH=/home/openvela/openvela-project/prebuilts/gcc/linux-x86_64/xtensa-esp32s3-elf/bin:$PATH
make -j4 EXTRAFLAGS="-Wno-cpp -Wno-deprecated-declarations"

# 5. Flash
echo "123" | sudo -S /home/openvela/openvela-project/myenv/bin/esptool.py --chip esp32s3 \
  --port /dev/ttyACM0 --baud 921600 --before default-reset --after hard-reset \
  write-flash -z --flash-mode dio --flash-freq 80m --flash-size 8MB 0x0 nuttx.bin

echo "=== DONE ==="
