# Contest 2026 team 212 (zhijianzhirongdui) — VelaMesh edge node app
# XIAO ESP32S3 Sense slave node: camera/face embedding, gait, BLE, MQTT uplink.
if(CONFIG_LVX_USE_DEMO_CONTEST2026_212_VELA_EDGE)
  nuttx_add_application(
    NAME vela_edge
    SRCS vela_edge_main.c
    STACKSIZE 4096)
endif()
