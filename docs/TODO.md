# 未完成项总表（TODO）

> 用途：把**除实机测试以外**的未完成项集中登记，避免散落在 `KNOWN_ISSUES.md`、
> `PACKAGE_LEDGER.md`、`FINAL_QA_PLAN.md` 与项目记忆中。
> 最近复核：2026-11-06（对照 `dist/Z24-mapeditor`、`locales/zh-CN/text_v2.csv` 与当前构建脚本）。
> 实机测试项不在此表：见 `docs/FINAL_QA_PLAN.md` §2.1 / §2.3 / §2.4 与 `docs/PACKAGE_LEDGER.md` §2。

## 1. 待办总表

| ID | 优先级 | 类别 | 待办 | 当前状态（2026-11-06 复核） | 建议下一步 | 关联文档 |
|---|---|---|---|---|---|---|
| **T-01** | 高 | 工程/存档兼容 | 载体码（cmap）固化：持久化「字→载体码」为 append-only，构建不再按字频重排 | **未实施**。仓库无 `locales/zh-CN/cmap.json`；`build_cn.build_plan()` 仍用 `cnt.most_common()`（`tools/build_cn.py:1113`）。后果：换补丁后存档自定义名会漂移 | 新增 `cmap.json`；`build_plan()` 优先读固化码，新字只从未用码/格追加；连续构建两次验证码不变，再用旧存档名字字节反查 | `KNOWN_ISSUES.md` §13、`PITFALLS.md` §27、`FINAL_QA_PLAN.md` §7 |
| **T-02** | 高 | 翻译质量 | 导入对话校对剩余 **451 条**（高严重度 14 条） | **未导入**。`dialogue_issues.tsv` 仍是 2272 条问题清单（无导入状态列）；Z19 只导入了 1821 单元 / 2842 处条目 | 逐条核对 451 条（优先 14 条高），按现有导入流程写回译表并重建基线 | `PROOFREAD_DIALOGUE_REPORT.md`、`KNOWN_ISSUES.md` §2、`TRANSLATING.md` §13 |
| **T-03** | 低 | 校对通道 | 歌词译文接入 `translator-view`（导出/导入） | **未接入**。`cscv[355]` 28 行为代码常量 `SONG_EN_LINES`（`tools/build_cn.py:2476`）；`export_review.py` 无歌曲表处理，校对视图看不到、改不了 | 如需要人工校对：为歌曲表增加导出/导入通道（JSON 或 TSV），并在导入后重建 | `PACKAGE_LEDGER.md` §5/2026-10-30 记录、`PITFALLS.md` §38 |
| **T-04** | 中 | 放行/未登记表 | 处理 collide 假命中与未登记显示表：`b630`、`b845`、`b1010`、`b892` | **未实施**。Z24 中 `b630`、`b845` 与母本字节差异 0；`b1010` 仍有 `handR=` 等 151 处；`b892` 装备视觉部件名等未放行 | 仿 `SONG_OK` 增加假命中放行清单；`b1010`/`b892` 走名字批次全副本同步后再登记 | `KNOWN_ISSUES.md` §12、`PACKAGE_LEDGER.md` §5 |
| **T-05** | 中 | 翻译缺口 | 补剩余机制/敌技名与说明短句 | **未补**。Z24 仍有：`1,000m/h Wind` / `10,000m/h Wind` 各 5 处（`b147/357/666/736`）；`Catch and Release` 2 处（`b172`）、`Beam Security`（`b444`）、`Thunder Storm Breath`（`b750`）；`b147/357/736/666` 说明短句；`b734` off5376 `Emperor Jelly` 1 处 | 技能名按完整机制名批次（含操作数重算）处理；说明短句按纯显示批次补译；逐条确认 `Emperor Jelly` 是否上屏 | `KNOWN_ISSUES.md` §21、`FINAL_QA_PLAN.md` §2.2、`PITFALLS.md` §42 |
| **T-06** | 中 | 专名审计 | 补齐专名审计覆盖面：DLC01 同表、脚本内联、未登记 UI；处理 `土おとこ` 漏译 | **未覆盖**。`PROOFREAD_NAME_REPORT.md` §2.3 已注明；`b928/59516`、`b928/67400` 两行把 `<超土おとこ>…` 整句省略为「它们就在村子北边！」 | 用「日文名 + 英文名」全库搜引用，补 DLC01 与脚本内联；按日文原文补回两行漏译 | `PROOFREAD_NAME_REPORT.md` §2.3/§7、`PITFALLS.md` §44 |
| **T-07** | 高 | 发布工程 | 将 Z22–Z24 的成果并入 Z19 / stable 基线，并决定敌名/Boss 名是否在基线放行 | **未并入**。`dist/Z19-proofread` 最后构建于 2026-11-04，早于 Z24 的 91 行专名统一与 `b291` 重译；Z19 配方（`do_package_names_cn_reuse_z19`）未启用 `HMH2_Z23_RELEASE`，stable 配方同样未启用 | 先决定基线是否放行图鉴敌名/Boss 名；再重建 Z19/stable，跑 `validate_build` 并刷新校对视图 | `PACKAGE_LEDGER.md` §2/§5、`BUILDING.md` §5.5、`README.md` 开发状态 |
| **T-08** | 低 | 已知取舍/演出 | 生僻字回退与 RAGNAROK 字幕同步 | **半开放**。2026-11-06 实测上屏缺字 0（新字形 2299/2847，余 548）；制作人员 `row1992` 的「崇」回退英文名；RAGNAROK 字幕仍略早于音频（暂不解决） | 生僻字按需扩容或接受现状；RAGNAROK 若处理，优先评估运行时字幕叠加方案 | `KNOWN_ISSUES.md` §7/§20、`tools/verify_charset_full.py` |

## 2. 复核证据（2026-11-06）

| ID | 复核方式 | 结果 |
|---|---|---|
| T-01 | 查仓库文件 + 读 `build_cn.build_plan()` | 无 `cmap.json`；第 1113 行仍 `cnt.most_common()` |
| T-02 | 读校对报告与 `dialogue_issues.tsv` | 451 条未导入（高 14）；TSV 无导入状态列 |
| T-03 | 搜 `export_review.py` / `build_cn.py` | 无歌曲表导出；`SONG_EN_LINES` 仍是代码常量 |
| T-04 | `s2a` 逐 blob 字节比对 Z24 vs 母本 | `b630`=0、`b845`=0；`b1010` 有改动但 `handR=` 仍 151 处；`b892` 部分改动 |
| T-05 | 在 Z24 `LANG_EN` 全库搜英文串 | Wind 各 5 处；Catch and Release 2、Beam Security 1、Thunder Storm Breath 1；`Jelly` 仅 1 处（`b734` off5376） |
| T-06 | 读报告 + 查 CSV | `b928/59516`、`b928/67400` 两行确实省略了名字 |
| T-07 | 读配方函数 + 检查 dist | `dist/Z19-proofread` 为 11-04 构建；Z19/stable 均未启用 `_Z23_RELEASE` |
| T-08 | 跑 `verify_charset_full.py` | 上屏缺字 0；新字形 2299/2847，余 548；`row1992` 显示英文原名 |

## 3. 不在此表的项

- **实机测试**：Z22/Z23/Z24 图鉴两页、战斗说话人、宝箱/掉落、DLC Q78 船、马/摩托/越野车/竹马、
  Mu/Xi 获取等，见 `docs/FINAL_QA_PLAN.md` §2.1。
- **明确不修**：Q16「勇者城」相关键名槽（`KNOWN_ISSUES.md` §4）、`Hero<>` 模板槽、
  `b509/908` 脚本键槽、称号 `b931 pos36`、`b317` 连携技表。
- **既定差异**：stable/E3 不含 4 个视频与 `cscv[355]` 歌词，是配方设计，不是缺漏。

## 4. 已同步的过期文档（2026-11-06）

- `README.md`：敌名未译、当前包状态、TODO 指针。
- `docs/KNOWN_ISSUES.md`：§1 名字类状态、§3 Z24 专名统一、§6 UI 词表已默认启用、
  §7 字库实测数字、§10.3 包状态表补 Z21–Z24、§21 `b34`/`Mu`/`Xi` 改判。
- `docs/PACKAGE_LEDGER.md`：最近更新日期、§5 `Jelly`/`Explanation` 已处理、症状表 TODO 指针。
- `docs/FINAL_QA_PLAN.md`：`b34` 已完成、剩余英文串精确位置、容量数字、TODO 指针。
- `docs/PROOFREAD_DIALOGUE_REPORT.md`、`docs/PROOFREAD_NAME_REPORT.md`：T-02/T-06 指针。
- `TRANSLATING.md`：字库容量实测数字、Z19 尚未并入 Z22–Z24。
