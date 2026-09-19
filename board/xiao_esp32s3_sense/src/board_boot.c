/****************************************************************************
 * Contest 2026 team 212 - XIAO ESP32S3 Sense board - boot stub
 *
 * Stage-1 placeholder so the board linkfile target builds. The real board
 * initialization (appinit / boot / bringup, camera DMA, network) has been
 * ported into ../reference/bsp and ../reference/camera from the team's
 * working openvela tree and is integrated by the follow-up bring-up task.
 ****************************************************************************/

#include <nuttx/board.h>

void openvela_board_initialize(void)
{
  /* Placeholder: hardware initialization arrives with board bring-up. */
}
