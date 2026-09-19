# ESP-NN S3 Assembly Path — A2 Breakthrough (OPE-49)

## TL;DR

The earlier "S3 assembly faults under the NuttX Xtensa ABI" diagnosis was
**wrong**. The assembly was never compiled into the firmware at all — the
ESP-NN Makefile only compiled the pure-C `_ansi.c` / `_opt.c` sources and
deliberately excluded every `.S` / `*_esp32s3.c` file. When the S3 dispatch
was enabled (`CONFIG_IDF_TARGET_ESP32S3`), `esp_nn_conv_s8` resolved to
`esp_nn_conv_s8_esp32s3` — a symbol that was **never compiled**, so the call
went to NULL → `EXCCAUSE=0x23 StoreProhibited VADDR=0`. That is not an ABI
fault; it is a missing-symbol fault caused by the build, not the runtime.

Fixing the build (compile the assembly) yields a firmware in which all 22
`_esp32s3` symbols are defined in `.text`. If the assembly runs correctly,
inference should drop from **25 s (pure-C) → ~1–1.4 s (S3 vector asm)**,
i.e. the ≤2 s target.

## Root cause

Two Makefiles cooperate to build ESP-NN + the TFLM esp_nn kernel port:

- `apps/mlearning/esp-nn/Makefile` — builds the ESP-NN library
- `apps/mlearning/tflite-micro/Makefile` — builds TFLM, sets `-DESP_NN`

The ESP-NN Makefile compiled only:

```make
CSRCS += .../esp_nn_conv_ansi.c       # always
CSRCS += .../esp_nn_conv_opt.c        # NN_OPTIMIZATIONS=1 (pure-C optimized)
```

and **never** the S3 sources (`esp_nn_conv_esp32s3.c`, `esp_nn_conv_s8_*_esp32s3.S`, …).
The comment in the Makefile said "those route to the S3 vector-instruction
kernels which fault under NuttX" — but they had never been compiled, so the
fault was from calling an absent symbol, not from the assembly itself.

`esp_nn.h` dispatch:

```c
#if defined(CONFIG_NN_OPTIMIZED)
#  ifdef CONFIG_IDF_TARGET_ESP32S3
#    define ARCH_ESP32_S3 1
#  endif
#endif
...
#if defined(ARCH_ESP32_S3)
#  include "esp_nn_esp32s3.h"   // routes esp_nn_conv_s8 -> esp_nn_conv_s8_esp32s3
#else
#  include "esp_nn_generic_opt.h" // routes esp_nn_conv_s8 -> esp_nn_conv_s8_opt (pure C)
#endif
```

Without `CONFIG_IDF_TARGET_ESP32S3`, dispatch goes to the pure-C `_opt`
kernels (which ARE compiled) → 25 s, works. With it enabled but the assembly
not compiled → dispatch to an undefined symbol → NULL call → crash.

## The fix

1. **`apps/mlearning/esp-nn/Makefile`** — when `CONFIG_IDF_TARGET_ESP32S3=y`,
   add `-DCONFIG_IDF_TARGET_ESP32S3` to CFLAGS and compile the S3 C wrappers
   (`CSRCS`) **and** the S3 Xtensa assembly (`ASRCS` — NuttX `Application.mk`
   compiles `.S` from `ASRCS`, not `CSRCS`).
2. **`apps/mlearning/tflite-micro/Makefile`** — when
   `CONFIG_IDF_TARGET_ESP32S3=y`, add `-DCONFIG_IDF_TARGET_ESP32S3` to
   `COMMON_FLAGS` so the TFLM `esp_nn/*.cc` kernels dispatch to the S3 path.
3. **`.config`** — `CONFIG_IDF_TARGET_ESP32S3=y`.

See the accompanying patch files:
- `esp-nn-Makefile-a2.patch`
- `tflm-Makefile-a2.patch`

## Verification (build-time, this branch)

```
$ xtensa-esp32s3-elf-nm nuttx | grep esp_nn | grep _esp32s3 | wc -l
22
$ xtensa-esp32s3-elf-nm nuttx | grep ' U esp_nn'          # undefined esp_nn
( empty — zero undefined symbols )
```

All 22 `_esp32s3` symbols are defined in `.text` (e.g.
`42214f94 T esp_nn_add_elementwise_s8_esp32s3`), including the four dispatch
targets that previously crashed: `esp_nn_conv_s8_esp32s3`,
`esp_nn_depthwise_conv_s8_esp32s3`, `esp_nn_add_elementwise_s8_esp32s3`,
`esp_nn_mul_elementwise_s8_esp32s3`.

## Runtime test plan (needs hardware)

Flash `nuttx.bin` (the A2 build) and capture the INFER line:

```
INFER: frame 1 (tot=…ms pre=… dcache=… invoke=… post=…) emb[0]=…
```

- **invoke ≈ 1000–1400 ms** → assembly works, ≤2 s target hit. Ship it.
- **invoke ≈ 25 s** → assembly compiled but dispatch still routes to pure-C
  (a header/macro mismatch); re-check `esp_nn.h` dispatch.
- **crash (StoreProhibited, VADDR != 0 this time)** → genuine ESP-NN assembly
  bug (see espressif/esp-nn issues #6/#7/#8 — some exist even on ESP-IDF).
  Then fall back to pure-C and pursue the smaller-model path.

If it crashes, the pure-C build is restored by setting
`# CONFIG_IDF_TARGET_ESP32S3 is not set` and rebuilding — the 25 s firmware
is the fallback.

## Build commands

```bash
# A2 (assembly) build
sed -i 's/^# CONFIG_IDF_TARGET_ESP32S3 is not set/CONFIG_IDF_TARGET_ESP32S3=y/' nuttx/.config
rm -f apps/mlearning/esp-nn/.built apps/mlearning/esp-nn/.depend
rm -f apps/mlearning/tflite-micro/.built apps/mlearning/tflite-micro/.depend
make -C nuttx -j$(nproc)

# Pure-C fallback
sed -i 's/^CONFIG_IDF_TARGET_ESP32S3=y/# CONFIG_IDF_TARGET_ESP32S3 is not set/' nuttx/.config
rm -f apps/mlearning/esp-nn/.built apps/mlearning/esp-nn/.depend
rm -f apps/mlearning/tflite-micro/.built apps/mlearning/tflite-micro/.depend
make -C nuttx -j$(nproc)
```

## Status

- Build: ✅ S3 assembly compiles and links under NuttX (22 defined symbols, 0 undefined)
- Runtime: ⏳ untested — needs a flash + boot on the XIAO ESP32-S3 Sense
