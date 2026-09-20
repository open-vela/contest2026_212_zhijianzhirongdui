#!/usr/bin/env bash
set -euo pipefail

node_id="edge-demo-01"
firmware_version="demo"
broker="mqtt://127.0.0.1:1883"
output_dir="./provision-output"
backend="stub"
confirmed="false"
flash_script=""
port="/dev/ttyACM0"

usage() {
  printf '%s\n' "用法: $0 [--node-id ID] [--firmware-version VER] [--broker URI] [--output-dir DIR]" \
    "          [--live --confirm-physical --flash-script FILE --port DEV]"
}

while (($#)); do
  case "$1" in
    --node-id) node_id="$2"; shift 2 ;;
    --firmware-version) firmware_version="$2"; shift 2 ;;
    --broker) broker="$2"; shift 2 ;;
    --output-dir) output_dir="$2"; shift 2 ;;
    --live) backend="serial"; shift ;;
    --confirm-physical) confirmed="true"; shift ;;
    --flash-script) flash_script="$2"; shift 2 ;;
    --port) port="$2"; shift 2 ;;
    -h|--help) usage; exit 0 ;;
    *) printf '错误：未知参数 %s\n' "$1" >&2; usage >&2; exit 2 ;;
  esac
done

[[ "$node_id" =~ ^[A-Za-z0-9._-]+$ ]] || {
  printf '错误：节点 ID 只能包含字母、数字、点、下划线和连字符。\n' >&2; exit 2;
}
[[ "$broker" == mqtt://* || "$broker" == mqtts://* ]] || {
  printf '错误：broker 必须使用 mqtt:// 或 mqtts:// URI。\n' >&2; exit 2;
}
if [[ "$backend" == "serial" ]]; then
  [[ "$confirmed" == "true" ]] || { printf '安全停止：live 模式必须传入 --confirm-physical。\n' >&2; exit 3; }
  [[ -n "$flash_script" && -x "$flash_script" ]] || { printf '错误：--flash-script 必须指向可执行烧录脚本。\n' >&2; exit 1; }
  [[ -c "$port" ]] || { printf '错误：串口不存在或不是字符设备：%s\n' "$port" >&2; exit 1; }
fi

mkdir -p "$output_dir"
registration="$output_dir/node-registration.json"
acl="$output_dir/mqtt-acl.conf"
explanation="$output_dir/explanation.log"

cat >"$registration" <<EOF
{
  "node_id": "$node_id",
  "firmware_version": "$firmware_version",
  "broker": "$broker",
  "backend": "$backend",
  "topics": [
    "edge/$node_id/face",
    "edge/$node_id/gait",
    "edge/$node_id/ble",
    "edge/$node_id/status"
  ],
  "state": "configuration_generated"
}
EOF

cat >"$acl" <<EOF
# 节点 $node_id 的最小发布权限
user $node_id
topic write edge/$node_id/face
topic write edge/$node_id/gait
topic write edge/$node_id/ble
topic write edge/$node_id/status
EOF

cat >"$explanation" <<EOF
[节点注册解释]
原因：管理员请求新增或修复边缘节点 $node_id。
动作：为固件 $firmware_version 生成独立身份、四类上行 topic 与最小发布权限。
后端：$backend。
风险：配置生成不代表硬件已烧录，也不代表节点已上线。
验证：hub 仍需收到 edge/$node_id/status 的真实上线消息。
EOF

printf '阶段 1/3：配置已生成：%s\n' "$registration"
printf '阶段 2/3：ACL 已生成：%s\n' "$acl"

if [[ "$backend" == "stub" ]]; then
  printf 'STUB：未访问串口、未烧录硬件、未伪造上线消息。\n' | tee -a "$explanation"
  printf '阶段 3/3：干跑完成；等待人工确认后才能进入真实烧录与上线验证。\n'
  exit 0
fi

printf '人工物理连接已确认；调用烧录管线。\n' | tee -a "$explanation"
"$flash_script" --port "$port" --confirm-flash
printf '烧录命令已完成；仍需通过真实 status 消息确认上线。\n' | tee -a "$explanation"
