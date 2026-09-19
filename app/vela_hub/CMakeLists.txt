# Contest 2026 team 212 (zhijianzhirongdui) — VelaMesh R528 fusion hub app
if(CONFIG_LVX_USE_DEMO_CONTEST2026_212_VELA_HUB)
  nuttx_add_application(
    NAME vela_hub
    SRCS vela_hub_main.c
    STACKSIZE 4096)
endif()
