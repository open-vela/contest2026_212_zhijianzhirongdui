# Contest 2026 team 212 - XIAO ESP32S3 Sense board - src
# Stage 1: only the boot stub participates in the build. The ported BSP and
# OV2640/OV3660 camera-DMA sources live in ../reference and are wired into the
# board library by the follow-up board-bring-up task.
nuttx_add_library(board)
target_sources(board PRIVATE board_boot.c)
