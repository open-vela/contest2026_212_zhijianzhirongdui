# VelaMesh (枢络) Portable Demo

This directory is the movable, offline runtime bundle. Copy `.env.example` to `.env`, build/export images on a prepared computer with `scripts\export-images.cmd`, then validate the copied folder on a second computer with the Internet disconnected.

At the venue run `scripts\start-demo.cmd` and open `http://127.0.0.1:8000/admin/demo`. Runtime data stays under `data/`; logs stay under `logs/`; `stop-demo.cmd` never removes them.

See `docs/competition-demo-runbook.md` in the repository for the full contract, modes, backup/restore and acceptance flow.
