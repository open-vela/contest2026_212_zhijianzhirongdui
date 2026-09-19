############################################################################
# Contest 2026 team 212 - VelaMesh edge node - Makefile
############################################################################

include $(APPDIR)/Make.defs

PROGNAME  = vela_edge
PRIORITY  = SCHED_PRIORITY_DEFAULT
STACKSIZE = 4096
MODULE    = $(CONFIG_LVX_USE_DEMO_CONTEST2026_212_VELA_EDGE)

# Stage 1: stub main only. The production sources under modules/ are added
# by follow-up tasks behind their feature guards (TFLITEMICRO, WiFi, BLE):
#   modules/camera    - OV2640/OV3660 DMA capture
#   modules/gait      - silhouette extraction
#   modules/inference - TFLM MobileFaceNet pipeline
#   modules/ble       - passive BLE proximity scan
#   modules/net       - MQTT uplink (xiaosense_network)
#   modules/tools     - host-side model conversion / VM source sync scripts
MAINSRC = vela_edge_main.c

include $(APPDIR)/Application.mk
