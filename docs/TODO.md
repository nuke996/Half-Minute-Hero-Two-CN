# 未完成项总表（TODO）

> 用途：把**除实机测试以外**的未完成项集中登记，避免散落在 `KNOWN_ISSUES.md`、
> `PACKAGE_LEDGER.md`、`FINAL_QA_PLAN.md` 与项目记忆中。
> 最近复核：2026-11-09（完成 T-01/T-02/T-07，新增 T-09）。
> 实机测试项不在此表：见 `docs/FINAL_QA_PLAN.md` §2.1 / §2.3 / §2.4 与 `docs/PACKAGE_LEDGER.md` §2。

## 1. 待办总表

| ID | 优先级 | 类别 | 待办 | 当前状态（2026-11-09 复核） | 建议下一步 | 关联文档 |
|---|---|---|---|---|---|---|
| **T-01** | 高 | 工程/存档兼容 | 载体码（cmap）固化：持久化「字→载体码」为 append-only，构建不再按字频重排 | **已完成（2026-11-09）**。新增 `locales/zh-CN/cmap.json`（2300 字）；`build_plan()` 优先使用固化码，新字只从池中未用码追加，旧字不重排；连续两次构建 `+0 新字`，LANG_EN/texture/cscv 哈希一致；2300 个码唯一且均可在字符表反查 | 无需手工维护；新增译字会自动追加。换补丁后用旧存档名字复测一次 | `KNOWN_ISSUES.md` §13、`PITFALLS.md` §27、`FINAL_QA_PLAN.md` §7 |
| **T-02** | 高 | 翻译质量 | 导入对话校对剩余 **429 条**（高严重度 0） | **已完成（2026-11-09）**：427 条已修复 + 2 条保留原译，共改动 529 处槽位（导入合计 530，另 1 处为既有人工修改）；`dialogue_issues_status.tsv` 剩余待核对 **0**；逐条原文/原译文/现译文见 `PROOFREAD_DIALOGUE_ROUND2.md`；Z24 重建 error 0 / warning 45 | 实机抽检本轮改动；后续新校对问题另开批次 | `PROOFREAD_DIALOGUE_REPORT.md`、`PROOFREAD_DIALOGUE_ROUND2.md`、`KNOWN_ISSUES.md` §2 |
| **T-03** | 低 | 校对通道 | 歌词译文接入 `translator-view`（导出/导入） | **未接入**。`cscv[355]` 28 行为代码常量 `SONG_EN_LINES`（`tools/build_cn.py:2481`）；`export_review.py` 无歌曲表处理，校对视图看不到、改不了 | 如需要人工校对：为歌曲表增加导出/导入通道（JSON 或 TSV），并在导入后重建 | `PACKAGE_LEDGER.md` §5/2026-10-30 记录、`PITFALLS.md` §38 |
| **T-04** | 中 | 放行/未登记表 | 处理 collide 假命中与未登记显示表：`b630`、`b845`、`b1010`、`b892` | **未实施**。Z24 中 `b630`、`b845` 与母本字节差异 0；`b1010` 仍有 `handR=` 等 151 处；`b892` 装备视觉部件名等未放行 | 仿 `SONG_OK` 增加假命中放行清单；`b1010`/`b892` 走名字批次全副本同步后再登记 | `KNOWN_ISSUES.md` §12、`PACKAGE_LEDGER.md` §5 |
| **T-05** | 中 | 翻译缺口 | 补剩余机制/敌技名与说明短句 | **未补**。Z24 仍有：`1,000m/h Wind` / `10,000m/h Wind` 各 5 处（`b147/357/666/736`）；`Catch and Release` 2 处（`b172`）、`Beam Security`（`b444`）、`Thunder Storm Breath`（`b750`）；`b147/357/736/666` 说明短句；`b734` off5376 `Emperor Jelly` 1 处 | 技能名按完整机制名批次（含操作数重算）处理；说明短句按纯显示批次补译；逐条确认 `Emperor Jelly` 是否上屏 | `KNOWN_ISSUES.md` §21、`FINAL_QA_PLAN.md` §2.2、`PITFALLS.md` §42 |
| **T-06** | 中 | 专名审计 | 补齐专名审计覆盖面：DLC01 同表、脚本内联、未登记 UI；处理 `土おとこ` 漏译 | **未覆盖**。`PROOFREAD_NAME_REPORT.md` §2.3 已注明；`b928/59516`、`b928/67400` 两行仍把 `<超土おとこ>…` 整句省略为「它们就在村子北边！」 | 用「日文名 + 英文名」全库搜引用，补 DLC01 与脚本内联；按日文原文补回两行漏译 | `PROOFREAD_NAME_REPORT.md` §2.3/§7、`PITFALLS.md` §44 |
| **T-07** | 高 | 发布工程 | 将 Z22–Z24 的成果并入 Z19 / stable 基线，并决定敌名/Boss 名是否在基线放行 | **已完成（2026-11-09）**。决策：**仅 Z19 放行 Z23 敌名/Boss 图鉴列表名**，stable/E3 保留原文作为安全回滚包。Z19 已启用 `HMH2_Z23_RELEASE` 并重建（LANG_EN `eb4bb2263f56`，error 0 / warning 45）；stable 已按当前译表重建（LANG_EN `2f7dae57bc10`，error 0 / warning 1），并登记进 `RECIPES` 以写正确清单 | 实机验证 Z19 图鉴/战斗说话人/宝箱后，再决定 stable 是否跟进放行 | `PACKAGE_LEDGER.md` §2/§5、`BUILDING.md` §5.5、`README.md` 开发状态 |
| **T-08** | 低 | 已知取舍/演出 | 生僻字回退与 RAGNAROK 字幕同步 | **半开放**。2026-11-09 实测上屏缺字 0（新字形 2300/2847，余 547）；制作人员 `row1992` 的「崇」回退英文名；RAGNAROK 字幕仍略早于音频（暂不解决） | 生僻字按需扩容或接受现状；RAGNAROK 若处理，优先评估运行时字幕叠加方案 | `KNOWN_ISSUES.md` §7/§20、`tools/verify_charset_full.py` |
| **T-09** | 高 | 分支管理 | 将 `proofread` 分支的最新进度合并回 `main` 主分支 | **未实施**。`proofread` 领先 `main` **26 个提交**、`main` 领先 0 个（可直接快进）：缺 2026-10/11 的对话校对、Z15–Z24 包谱系、T-01 的 `cmap.json` 固化、T-02 第二轮校对等 | 提交本轮工作后，在 `main` 上 `git merge --ff-only proofread`（或 PR 合并）；随后按 `tools/build.py package_current` / `package_names_cn_reuse_z19` / `package_stable_names` 重建并跑 `validate_build` | `docs/TODO.md`、`BUILDING.md` §9 |

## 2. 复核证据（2026-11-09）

| ID | 复核方式 | 结果 |
|---|---|---|
| T-01 | 读 `cmap.json` + 连续两次 `package_current` | 2300 字；第二次 `+0 新字`；LANG_EN/texture/cscv/DLC01 哈希与第一次一致；2300 码唯一且均可反查 |
| T-02 | 读 `dialogue_issues_status.tsv` | 待核对 0；已修复 427 + 保留原译 2；`import_review` 收到 530 处修订（529 本轮 + 1 既有）；error 0 / warning 45 |
| T-03 | 搜 `export_review.py` / `build_cn.py` | 无歌曲表导出；`SONG_EN_LINES` 仍是代码常量 |
| T-04 | `handR=` / `foot=` 计数 Z24 vs 母本 | 各 151 处，未处理 |
| T-05 | 在 Z24 `LANG_EN` 全库搜英文串 | Wind 各 5 处；Catch and Release 2、Beam Security 1、Thunder Storm Breath 1；Jelly 1 处 |
| T-06 | 读报告 + 查 CSV | `b928/59516`、`b928/67400` 两行确实省略了名字 |
| T-07 | 读新配方 + 检查 dist | Z19 `HMH2_Z23_RELEASE=1` 且 LANG_EN 与 Z24 同哈希；stable `=0`，LANG_EN `2f7dae57bc10`；两者 validate error 0 |
| T-08 | 2026-11-06 `verify_charset_full.py` + 2026-11-09 构建输出 | 上屏缺字 0；新字形 2300/2847，余 547；`row1992` 显示英文原名 |
| T-09 | `git branch` / `git log` | `proofread` 领先 `main`；需合并（未执行） |

## 3. 不在此表的项

- **实机测试**：Z22/Z23/Z24 图鉴两页、战斗说话人、宝箱/掉落、DLC Q78 船、马/摩托/越野车/竹马、
  Mu/Xi 获取等，见 `docs/FINAL_QA_PLAN.md` §2.1。
- **明确不修**：Q16「勇者城」相关键名槽（`KNOWN_ISSUES.md` §4）、`Hero<>` 模板槽、
  `b509/908` 脚本键槽、称号 `b931 pos36`、`b317` 连携技表。
- **既定差异**：stable/E3 不含 4 个视频与 `cscv[355]` 歌词，是配方设计，不是缺漏。

## 4. 已同步的过期文档

**2026-11-09（本轮）：**
- `README.md`：开发状态、T-02/T-01/T-07 完成、T-09 指针。
- `docs/KNOWN_ISSUES.md`：§2 待核对清零、§13 cmap 已实施、§10.3 Z19/stable 状态。
- `docs/FINAL_QA_PLAN.md`：§2.4 剩余清零、§4 导入目标、§7 cmap 已完成。
- `docs/PACKAGE_LEDGER.md`：Z19/stable/Z24 哈希与 T-07 决策、§5 剩余项。
- `docs/PROOFREAD_DIALOGUE_REPORT.md`：剩余 451 → 0，指向第二轮报告。
- `TRANSLATING.md`：§13 校对进度、§16/§17 载体码固化。
- `BUILDING.md`：§5.5 配方说明、§9 新增 `cmap.json` 说明。
- `docs/PITFALLS.md` §27：cmap 固化由“尚未实施”改为“已实施”。

**2026-11-06（上一轮）：**
- `README.md`：敌名未译、当前包状态、TODO 指针。
- `docs/KNOWN_ISSUES.md`：§1 名字类状态、§3 Z24 专名统一、§6 UI 词表已默认启用、
  §7 字库实测数字、§10.3 包状态表补 Z21–Z24、§21 `b34`/`Mu`/`Xi` 改判。
- `docs/PACKAGE_LEDGER.md`：最近更新日期、§5 `Jelly`/`Explanation` 已处理、症状表 TODO 指针。
- `docs/FINAL_QA_PLAN.md`：`b34` 已完成、剩余英文串精确位置、容量数字、TODO 指针。
- `docs/PROOFREAD_DIALOGUE_REPORT.md`、`docs/PROOFREAD_NAME_REPORT.md`：T-02/T-06 指针。
- `TRANSLATING.md`：字库容量实测数字、Z19 尚未并入 Z22–Z24。
