#!/usr/bin/env bash
set -euo pipefail

project_dir="${HOME}/openvela-project/nuttx"
venv_dir="${HOME}/openvela-project/myenv"
toolchain_dir="${HOME}/openvela-project/prebuilts/gcc/linux-x86_64/xtensa-esp32s3-elf/bin"
port="/dev/ttyACM0"
elf_name="nuttx"
image_name="nuttx_x.bin"
mode="all"
confirmed="false"

usage() {
  printf '%s\n' "用法: $0 [--project-dir DIR] [--venv DIR] [--toolchain DIR] [--port DEV]" \
    "          [--elf FILE] [--image FILE] [--build-only|--image-only] [--confirm-flash]"
}

while (($#)); do
  case "$1" in
    --project-dir) project_dir="$2"; shift 2 ;;
    --venv) venv_dir="$2"; shift 2 ;;
    --toolchain) toolchain_dir="$2"; shift 2 ;;
    --port) port="$2"; shift 2 ;;
    --elf) elf_name="$2"; shift 2 ;;
    --image) image_name="$2"; shift 2 ;;
    --build-only) mode="build"; shift ;;
    --image-only) mode="image"; shift ;;
    --confirm-flash) confirmed="true"; shift ;;
    -h|--help) usage; exit 0 ;;
    *) printf '错误：未知参数 %s\n' "$1" >&2; usage >&2; exit 2 ;;
  esac
done

[[ -d "$project_dir" ]] || { printf '错误：工程目录不存在：%s\n' "$project_dir" >&2; exit 1; }
[[ -f "$venv_dir/bin/activate" ]] || { printf '错误：虚拟环境不存在：%s\n' "$venv_dir" >&2; exit 1; }
[[ -d "$toolchain_dir" ]] || { printf '错误：工具链目录不存在：%s\n' "$toolchain_dir" >&2; exit 1; }

# shellcheck disable=SC1090
source "$venv_dir/bin/activate"
export PATH="$toolchain_dir:$PATH"
cd "$project_dir"

if [[ "$mode" != "image" ]]; then
  printf '开始编译：make -j4\n'
  make -j4
  [[ -f "$elf_name" ]] || { printf '错误：编译结束但未找到 ELF：%s/%s\n' "$project_dir" "$elf_name" >&2; exit 1; }
  printf '验证：已生成 ELF %s\n' "$elf_name"
fi

if [[ "$mode" == "build" ]]; then
  exit 0
fi

command -v esptool.py >/dev/null || { printf '错误：venv/PATH 中找不到 esptool.py\n' >&2; exit 1; }
[[ -f "$elf_name" ]] || { printf '错误：找不到待打包 ELF：%s/%s\n' "$project_dir" "$elf_name" >&2; exit 1; }

printf '开始生成 RAM-only-header 镜像：%s\n' "$image_name"
esptool.py --chip esp32s3 elf2image --ram-only-header -fs 8MB -fm dio -ff 40m \
  -o "$image_name" "$elf_name"
[[ -s "$image_name" ]] || { printf '错误：镜像未生成或为空：%s\n' "$image_name" >&2; exit 1; }

if [[ "$mode" == "image" ]]; then
  printf '验证：镜像已生成（未烧录）：%s\n' "$image_name"
  exit 0
fi

if [[ "$confirmed" != "true" ]]; then
  printf '安全停止：镜像已生成，但未收到 --confirm-flash；未访问串口、未烧录。\n' >&2
  exit 3
fi
[[ -c "$port" ]] || { printf '错误：串口不存在或不是字符设备：%s\n' "$port" >&2; exit 1; }

printf '释放 picocom 占用（若存在）\n'
killall -9 picocom 2>/dev/null || true
printf '开始烧录：端口=%s，地址=0x0\n' "$port"
esptool.py --chip esp32s3 --port "$port" --baud 921600 \
  --before default-reset --after hard-reset write-flash -z \
  --flash-mode dio --flash-freq 40m --flash-size 8MB 0x0 "$image_name"
printf '烧录命令完成；请继续采集串口日志验证应用层启动。\n'

