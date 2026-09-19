#!/usr/bin/env python3
"""Pull key source files from VM into the zhijian project."""
import subprocess, os

VM = "openvela@192.168.25.131"
BOARD = "boards/xtensa/esp32s3/xiao-esp32s3-sense"
NUTTX = "/home/openvela/openvela-project/nuttx"

files = [
    # Camera / DMA
    f"{NUTTX}/{BOARD}/src/esp32s3_camera_dma.c",
    f"{NUTTX}/{BOARD}/src/esp32s3_camera_dma.h",
    # Board bringup
    f"{NUTTX}/{BOARD}/src/esp32s3_bringup.c",
    f"{NUTTX}/{BOARD}/src/xiao_esp32s3_regs.h",
    f"{NUTTX}/{BOARD}/src/esp32s3_boot.c",
    f"{NUTTX}/{BOARD}/src/esp32s3_appinit.c",
    # Board config
    f"{NUTTX}/{BOARD}/src/xiao-esp32s3-sense.h",
    f"{NUTTX}/{BOARD}/include/board.h",
    # TFLite Micro wrapper
    f"{NUTTX}/{BOARD}/src/tflm_wrapper.h",
    # WiFi / Network
    f"{NUTTX}/{BOARD}/src/xiaosense_network.c",
    f"{NUTTX}/{BOARD}/src/xiaosense_network.h",
]

# Target: zhijian/embedded/camera/ — all VM source files go here
local_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "camera")
os.makedirs(local_dir, exist_ok=True)

pulled = []
failed = []
for f in files:
    basename = os.path.basename(f)
    local_path = os.path.join(local_dir, basename)
    print(f"Pulling: {basename}...", end=" ")
    result = subprocess.run(
        ["ssh", "-o", "StrictHostKeyChecking=no", VM, f"cat '{f}'"],
        capture_output=True, text=True, timeout=15
    )
    if result.returncode == 0:
        with open(local_path, "w", encoding="utf-8", errors="replace") as fh:
            fh.write(result.stdout)
        print(f"{len(result.stdout)} bytes")
        pulled.append(basename)
    else:
        print(f"SKIPPED: {result.stderr.strip()}")
        failed.append((basename, result.stderr.strip()))

print(f"\n=== Pulled {len(pulled)} files ===")
for n in pulled:
    print(f"  + {n}")

if failed:
    print(f"\n=== Failed {len(failed)} files ===")
    for n, err in failed:
        print(f"  - {n}: {err}")

print(f"\nAll saved to: {local_dir}")
