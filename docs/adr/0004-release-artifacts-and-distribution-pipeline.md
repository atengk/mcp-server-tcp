# 0004: GitHub Release 分发制品打包与校验清单挂载

针对项目多渠道分发需求，确立在 GitHub Release 自动化发版流程中编译并挂载与 PyPI 完全一致的打包制品及完整性校验清单。

## 背景与问题

1. **用户离线与手动安装需求**：部分开发者和离线/内网环境无法直连 PyPI，需要直接在 GitHub Release 页面下载 `.whl` 或 `.tar.gz` 进行离线安装；
2. **多渠道制品一致性**：若 GitHub Release 仅发布 Git Tag 源码快照而无编译制品，会导致 GitHub Release 与 PyPI 官方包处于割裂状态；
3. **安全审计与完整性防御**：下载二进制制品时缺乏快速可靠的校验手段，需要随包提供官方生成的 SHA-256 校验和清单。

## 决策内容

1. **Release 工作流内置自闭环构建**：
   - 在 `.github/workflows/release.yml` 的 `github-release` job 中引入 `astral-sh/setup-uv`；
   - 执行 `uv build`，编译生成标准 `sdist`（`.tar.gz`）与 `wheel`（`.whl`）制品至 `dist/` 目录；
   - 自动生成 `checksums.txt`（包含 `dist/` 下除校验和文件外的所有构建制品 SHA-256 哈希）。
2. **松耦合双轨发布**：
   - GitHub Release（`release.yml`）与 PyPI 发布（`publish.yml`）保持独立触发与构建，避免单点阻塞；
   - Release 页面自动挂载 `dist/*.tar.gz`、`dist/*.whl` 与 `dist/checksums.txt`。
3. **存量 Release 补全策略**：
   - 针对当前已发行的 `v1.0.0` 正式版本，通过 CLI 工具补充上传本地对应构建的同版本二进制制品与校验清单，确保版本发布的完整性。
