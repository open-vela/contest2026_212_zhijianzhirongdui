# 枢络 VelaMesh Skills

本目录把同一条“边缘节点接入”链路拆成两个层次：开发机上的
`esp32s3-flash-pipeline` 负责构建、打包、烧录和串口取证；R528 hub 上的
`edge-node-provisioning` 负责生成节点身份与 MQTT 配置，并在人工确认物理连接后调用前者。

## 技能与触发词

| 层次 | 技能 | 典型触发词 | 入口 |
|---|---|---|---|
| 开发时 | `esp32s3-flash-pipeline` | “烧录”“刷机”“flash ESP32-S3”“边缘节点固件” | `esp32s3-flash-pipeline/SKILL.md` |
| R528 运行时 | `edge-node-provisioning` | “新增边缘节点”“注册边缘节点”“节点固件失配”“节点反复重启” | `runtime/edge-node-provisioning/edge-node-provisioning.md` |

## R528 部署

openvela `packages/ai_agent` 当前的权威实现会扫描 `/data/agent/skills/*.md`，而不是扫描
子目录，也不读取 `manifest.json`。部署时将运行时技能复制成单文件：

```sh
adb push runtime/edge-node-provisioning/edge-node-provisioning.md \
  /data/agent/skills/edge-node-provisioning.md
```

首次启动或重启 agent 后，它会从标题和首段描述建立技能摘要。仓内的 `scripts/` 是演示及
人工执行资源，不应整体复制到 `/data/agent/skills/` 后期待 agent 自动执行。

## 无硬件演示

```sh
skills/runtime/edge-node-provisioning/scripts/provision_demo.sh \
  --node-id edge-demo-01 --firmware-version 0.1.0 --output-dir ./demo-output
```

默认使用 stub 串口后端，不写串口、不烧录硬件；输出节点注册记录、MQTT ACL 和中文解释日志。
真实部署前必须由操作者确认目标板、串口和固件，并显式传入 `--live --confirm-physical`。

