# logs/ — AI Coding 日志目录

存放开发中与 AI 工具的对话日志，和作品代码一并提交。

本仓已按[《AI Coding 日志归集与提交手册》](https://github.com/open-vela/docs/blob/dev-ai-contest-2026/zh-cn/contest_2026/ai_coding_log_guide.md)
用组委会归集工具（`contest-log-collector`，claude-code adapter 1.3.0）导出本队
真实会话，示例目录 `your-github-login/` 已删除。

## 目录结构

```text
logs/
└── FlyFei71/                    # GitHub 用户名（单人参赛，一人一目录）
    ├── manifest.json            # 会话清单（schema 1.0）
    └── 2026-09-20/              # 按归集工具本地日期分桶
        ├── claude-code__ad3d3c35-….jsonl
        ├── claude-code__ce310476-….jsonl
        └── claude-code__58c26617-….jsonl
```

- 3 个会话均为 Claude Code CLI 采集（`collection_mode: cli`），通过官方
  `export-session.py` 从本机 `~/.claude/projects/` 原始转录回填导出，未手工编辑。
- 每个 `.jsonl` 每行一个事件（`seq` 连续），只提交 JSONL 本身。
- 已按归集工具默认规则脱敏 `ghp_*` token，并追加规则脱敏本机
  `ark-*` 网关令牌与 GitHub PAT 明文；受影响事件带 `redacted_count` 字段。
- 校验：`python tools/validate-log.py logs/` → ✔ ALL OK（3 文件 / 事件数以
  manifest 为准）。

后续开发日继续用 `contest-snapshot`（SessionEnd 自动导出或
`contest-snapshot --today --confirm`）追加，提交时使用 `git commit -s`。
