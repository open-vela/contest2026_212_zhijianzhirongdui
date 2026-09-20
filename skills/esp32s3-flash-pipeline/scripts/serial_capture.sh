#!/usr/bin/env bash
set -euo pipefail

port="/dev/ttyACM0"
rounds=2
duration=25
restart_wait=35
output_dir="./serial-evidence"

usage() {
  printf '%s\n' "用法: $0 [--port DEV] [--rounds N] [--duration SEC] [--restart-wait SEC] [--output-dir DIR]"
}

while (($#)); do
  case "$1" in
    --port) port="$2"; shift 2 ;;
    --rounds) rounds="$2"; shift 2 ;;
    --duration) duration="$2"; shift 2 ;;
    --restart-wait) restart_wait="$2"; shift 2 ;;
    --output-dir) output_dir="$2"; shift 2 ;;
    -h|--help) usage; exit 0 ;;
    *) printf '错误：未知参数 %s\n' "$1" >&2; usage >&2; exit 2 ;;
  esac
done

[[ "$rounds" =~ ^[1-9][0-9]*$ && "$duration" =~ ^[1-9][0-9]*$ && "$restart_wait" =~ ^[0-9]+$ ]] || {
  printf '错误：轮数和秒数必须是正整数（等待时间可为 0）。\n' >&2; exit 2;
}
[[ -c "$port" ]] || { printf '错误：串口不存在或不是字符设备：%s\n' "$port" >&2; exit 1; }
command -v timeout >/dev/null || { printf '错误：找不到 timeout 命令。\n' >&2; exit 1; }
mkdir -p "$output_dir"

for ((round=1; round<=rounds; round++)); do
  log_file="$output_dir/serial-round-${round}.log"
  printf '采集第 %d/%d 轮：%s 秒 -> %s\n' "$round" "$rounds" "$duration" "$log_file"
  status=0
  timeout "$duration" cat "$port" | tee "$log_file" || status=$?
  if [[ "$status" -ne 0 && "$status" -ne 124 ]]; then
    printf '错误：串口采集失败，退出码=%d\n' "$status" >&2
    exit "$status"
  fi
  if [[ "$round" -lt "$rounds" ]]; then
    printf '等待 %s 秒，准备捕获可能的二次启动。\n' "$restart_wait"
    sleep "$restart_wait"
  fi
done
printf '采集完成；请检查日志中的启动、WiFi/BLE 初始化及状态上报证据。\n'

