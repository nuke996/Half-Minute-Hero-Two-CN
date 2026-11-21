# 未完成项总表（TODO）

> 用途：把**除实机测试以外**的未完成项集中登记，避免散落在 `KNOWN_ISSUES.md`、
> `PACKAGE_LEDGER.md`、`FINAL_QA_PLAN.md` 与项目记忆中。
> 最近复核：2026-11-21（T-10b/T-11/T-12/T-13a/T-07b 已落地并重建 Z27/Z19/stable；
> 仅剩 `row 20447` 按钮语义待实机、P3 收尾项与实机测试）。
> 上一轮 2026-11-15：修正 T-04b（游戏内显示已完成，剩余校对视图登记）。
> 2026-11-13：T-09 完成，`proofread` 快进合并入 `main`，后续开发以 `main` 为主分支。
> 实机测试项不在此表：见 `docs/FINAL_QA_PLAN.md` §2.1 / §2.3 / §2.4 与 `docs/PACKAGE_LEDGER.md` §2。

## 1. 待办总表

### 1.1 P0（先做，用户可见的内容/功能错误）

（当前无。）

### 1.2 P1（发布前必须处理）

| ID | 类别 | 待办 | 当前状态（2026-11-21 复核） | 建议下一步 | 关联文档 |
|---|---|---|---|---|---|
| **T-13a** | 术语表/方向拍板 | 术语表按推荐表定向；确认阻塞项方向 | **已完成（2026-11-21）**。术语表已按推荐表定向：`おじさま→大叔`、`銃士→火枪手`、`ウォーリア→勇士`、`エクスペリダイブ→经验俯冲`、`登場セリフ→出场台词`、`アイテム→道具`、`悪ガキ→小鬼`；`魔王ケルベロス→刻耳柏洛斯`、`テント→帐篷`、`歌族`、`海岸人鱼`、`黄金冲击`、`赞特赫尔`、`辛多尼克斯`、`贝塔`、`红萝卜老爷` 均已落表。`アヴァ`/`スペルヴィア` 因 EN 槽位仅 3/7 字节回退为「艾」/「斯佩维」（§13） | 无；新增术语先按 §13 做容量评估，再进术语表 | `TERM_RECOMMENDATIONS_20261121.md` §5、`术语表.md` §3–§13、`tools/audit_terms.py` |
| **T-10b** | 术语/误译/漏译 | 第一批高置信误译与漏译（原 T-10 主体 + T-06 漏名 + T-05c 遗留） | **已完成（2026-11-21 Z27），1 项待实机**。① `船頭` 13/13→船夫；③ `extra::417::206540`→超新流星；④ `row::6113`→火枪手、`row::10938`→魔法师之路；⑤ `おじさま` 47 处（CSV 39 + extra 1 + DLC 7）→大叔，`火枪手` 全表 7；⑥ `row::53227/53228/53242/53243` 超土おとこ 四行重排，统一为「超级泥浆怪/超级泥浆王」；⑦ `Hellfire`/`Dogry`/`Reusable` 在译表 0 命中（仅二进制副本，非显示串），`Venus Seven` 仅首次括注，登记例外。② `row 20447` 日文 `キャンセル` / 英文 `Continue`，暂保留「继续」 | 实机确认 `row 20447` 暂停菜单按钮语义；若确认为 Continue 则登记例外，否则改「取消」 | `TERM_RECOMMENDATIONS_20261121.md` §2.1/§6、`KNOWN_ISSUES.md` §21 |
| **T-07b** | 发布工程 | 重建 Z19 / stable 发布基线，并入 Z25–Z27 与术语批次 | **已完成（2026-11-21，工作树 dirty）**。Z19 `LANG_EN 1b0109baf96a` / texture `fb5b79e17e37` / cscv `f074004c8eb3` / DLC01 `bbe1e4a87b61` / MOV `237ee86d26f6`；stable `LANG_EN 155e2b3784b9` / cscv `8f0bd9db2a40` / DLC01 `d139508e35c0`；Z27 与 Z19 内容一致。validate：Z19/Z27 error 0 / warning 46（+1 为「对话设置」同串），stable error 0 / warning 1。`build_manifest` 均为 git `a642734 (dirty)` | 提交后从干净 `main` 复跑一次以消除 manifest 的 dirty 标记；实机验证 Z19 后替换发布包 | `PACKAGE_LEDGER.md` §2/§5、`BUILDING.md` §5.5 |

### 1.3 P2（发布前建议处理）

| ID | 类别 | 待办 | 当前状态（2026-11-21 复核） | 建议下一步 | 关联文档 |
|---|---|---|---|---|---|
| **T-11** | 术语/专名统一 | 术语表 §12 与专名批量统一 | **已完成（2026-11-21 Z27）**。`歌之族`/`陆地鱼人`/`陆鱼人`/`淘金热`/`瑟伯勒斯`/`赞特地狱`/`辛多尼斯`/`红萝卜老伯`/`坏小子` 全部归零；`歌族`、`海岸人鱼`、`海岸人鱼姐妹`、`黄金冲击`（含复合槽 7966/7988）、`刻耳柏洛斯`、`赞特赫尔`、`辛多尼克斯`、`贝塔`、`红萝卜老爷` 已统一。`アヴァ` 保留「艾」、`スペルヴィア` 保留「斯佩维」：EN 槽位仅 3/7 字节，长形式会触发名字一致性校验 error（见 §13/PITFALLS） | 无；后续新增专名先查 §13 容量 | `TERM_RECOMMENDATIONS_20261121.md` §2.1/§2.2、`术语表.md` §12、`term_review_recommendations_20261121.tsv` |
| **T-12** | 术语/说话人标签 | 说话人标签统一（97 组） | **已完成主体（2026-11-21 Z27）**。97 组降至 40 组；`副隊長ヤーシュ→副队长亚修` 已统一；专有人名、店铺标签、泛称人物按推荐表批量处理。剩余 40 组均为 `保留差异`（主人/おやじ/店主/老人/おばさん/学者/マスター/おじさん/めしや 等）或按语境差异；`巻物`/`ババ` 误报未动 | 剩余为设计上的语境差异，不再批量替换；新增说话人先按推荐表 §3/§4 判断 | `speaker_label_variants_20261121.tsv`、`TERM_RECOMMENDATIONS_20261121.md` §3/§4 |

### 1.4 P3（收尾项，不影响发布）

| ID | 类别 | 待办 | 当前状态（2026-11-21 复核） | 建议下一步 | 关联文档 |
|---|---|---|---|---|---|
| **T-04** | 放行/未登记表 | 纯显示串与 collide 假命中放行（原 T-04a + T-05a） | **部分完成（2026-11-21 Z27）**。复核 5427 条 protected 后，补放行 11 个 collide 假命中：b906 记忆检查三个选项、b34 无限关卡名 2 条、b186 名字输入说明、b282 图鉴简介 2 条、b757 奖励消息 2 条、b905 事件台词；均已上屏并 `validate_build` error 0。`Check`/`Sing`/`入る`/`こうげき` 等命令键确认应保持保护。仍剩 `b630`/`b845` 假命中未登记；`b357 off122396/122664` 的 `Large Attack`/`Heavy Attack`、`b666` 的 `Trigger Rate: 1/x` 20 种均不在译表（0 命中） | 定性 `Large/Heavy Attack`：若为装备名则升 P2；`Trigger Rate` 按 UI 文案补登记；继续按 `(blob, offset)` 复核剩余 protected | `KNOWN_ISSUES.md` §12/§21、`PACKAGE_LEDGER.md` §5 |
| **T-03** | 校对视图/歌词 | 非 CSV 表接入校对视图（原 T-03 + T-04b） | **未实施**。`SONG_EN_LINES` 28 条仍为代码常量（[`build_cn.py`](../tools/build_cn.py) 第 2601 行，原文档写的 2481 已过期）；`export_review.py` 无歌曲表与内嵌副本处理；`text_v2.csv` 的 b34 共 317 行但均为章节/曲目标题，没有 `head/body/...` 装备名行 | 为歌曲表与内嵌装备名副本增加导出/导入通道；导入写回权威道具表 `b147/357/736/998`；`Villager's Clothes`×2、`Hellfire`×1 放入 `protected/` 或标注跳过原因；每批重建并导出视图 | `PACKAGE_LEDGER.md` §5、`PITFALLS.md` §38、`KNOWN_ISSUES.md` §12 |
| **T-08** | 已知取舍/演出 | 生僻字回退与 RAGNAROK 字幕同步 | **半开放**。2026-11-09 实测上屏缺字 0；`cmap.json` 现为 **2304/2847（余 543，原文档写的 2300/547 已过期）**；制作人员 `row1992` 的「崇」回退英文名；RAGNAROK 字幕仍略早于音频 | 生僻字按需扩容或接受现状；RAGNAROK 若处理，优先评估运行时字幕叠加方案 | `KNOWN_ISSUES.md` §7/§20、`tools/verify_charset_full.py` |

### 1.5 已完成（保留记录）

| ID | 完成时间 | 结果 | 关联文档 |
|---|---|---|---|
| **T-01** | 2026-11-09 | 载体码（cmap）固化，`locales/zh-CN/cmap.json` 为 append-only；连续构建 `+0 新字`，哈希一致 | `KNOWN_ISSUES.md` §13、`PITFALLS.md` §27 |
| **T-02** | 2026-11-09 | 导入对话校对 429 条清零（427 修复 + 2 保留原译，529 槽）；Z24 重建 error 0 / warning 45 | `PROOFREAD_DIALOGUE_ROUND2.md` |
| **T-05b** | 2026-11-15（Z25） | Wind 两技能 10 槽 + 敌技显示名 9 槽中文化；仅 4 个操作数变化；validate error 0 / warning 45 | `dist/Z25-mech-names/`、`KNOWN_ISSUES.md` §21 |
| **T-05c** | 2026-11-15（Z26） | 47 槽 / 44 个敌技显示名；操作数 0 变化；cmap +4（2304）。**遗留项已转入 T-10b**：`Hellfire`、`Venus Seven`、`Dogry`、`Reusable` | `dist/Z26-enemy-skills/` |
| **T-07** | 2026-11-09（2026-11-12 重建） | Z22–Z24 并入 Z19/stable；仅 Z19 放行敌名/Boss 图鉴名。**发布基线后续更新见 T-07b** | `PACKAGE_LEDGER.md` §2/§5 |
| **T-09** | 2026-11-13 | `proofread` 28 个提交快进合并入 `main`；三个包从 `main` 重建校验通过 | `PACKAGE_LEDGER.md` §6 |
| 术语清理（无独立 ID） | 2026-11-21 | 提交 `b76af42` 统一 `グリモワール/グリモ→魔法书`，`魔典/格瑞莫/格里莫` 在 `zh_new` 已归零；Z27 完成 27 个选项放行、15 个尾行留空、副队长统一（`validate_build` error 0 / warning 45） | `docs/TEMP_REVIEW_20261121.md`、`PACKAGE_LEDGER.md` §2 |
| **T-10b/T-11/T-12/T-13a/T-07b** | 2026-11-21（Z27/Z19/stable） | `船頭/おじさま/銃士/魔道士/悪ガキ/超新流星` 等第一批误译落地；专名与说话人标签批量统一（97→40 组）；`audit_terms` 161→72（P1 0）。重建 Z19/stable/Z27：validate error 0，warning Z19/Z27 46、stable 1；哈希见 `PACKAGE_LEDGER` §2 | `docs/TERM_RECOMMENDATIONS_20261121.md`、`术语表.md`、`PACKAGE_LEDGER.md` §2 |

### 1.6 旧 ID 对照（供其他文档引用）

| 旧 ID | 新归属 | 说明 |
|---|---|---|
| T-04a | **T-04** | 与 T-05a 合并为「纯显示串与假命中放行」 |
| T-04b | **T-03** | 与旧 T-03（歌词）合并为「非 CSV 表接入校对视图」 |
| T-05a | **T-04** | 剩余项同上 |
| T-05c | 已完成；遗留项进 **T-10b** | `Hellfire`/`Venus Seven`/`Dogry`/`Reusable` |
| T-06 | **T-10b**（4 行漏名）+ **T-04**（覆盖登记） | 原「补齐专名审计覆盖面」拆分 |
| T-10 | **T-10b**（误译/漏译） | 按严重度收拢后的批次 |
| T-13 | **T-13a**（术语表定向）+ T-07b 检查清单 | 流程固化并入发布检查 |

## 2. 复核证据

### 2.1 2026-11-21

| ID | 复核方式 | 结果 |
|---|---|---|
| T-13a | 读 `术语表.md` §3–§13 + 复跑 audit | 推荐条目已全部落表；`アヴァ`/`スペルヴィア` 按 §13 容量回退 |
| T-10b | 读 `text_v2.csv`/`extra_review.json`/`ml_zh_fields.json`/DLC 表 | 已完成：`船頭` 13/13→船夫、`おじさま` 47→大叔、`銃士`→火枪手、`超新流星`；`row 20447` 保留「继续」待实机 |
| T-07b | 读 `dist/` 与 `PACKAGE_LEDGER.md` §2 | Z19/stable/Z27 已重建，validate error 0（Z19/Z27 warning 46、stable 1） |
| T-11 | 计数 `zh_new` 字段 | `歌之族`/`陆地鱼人`/`淘金热`/`瑟伯勒斯`/`赞特地狱`/`辛多尼斯` 归零；`艾`/`斯佩维` 为容量回退 |
| T-12 | 计数 `zh_new` + Z27 记录 | `二当家` 0、`副队长` 14；Z27 已统一副队长；本批次后 97→40 组（见下行） |
| T-04 | 搜全译表 + 读 `build_cn.py` 放行清单 | `Large/Heavy Attack`、`Trigger Rate` 0 命中；无 `b630`/`b845` 放行项 |
| T-03 | 读 `build_cn.py` / `export_review.py` / `text_v2.csv` b34 | `SONG_EN_LINES` 28 条（第 2601 行）；导出脚本无歌曲/内嵌副本；b34 无装备名行 |
| T-08 | 读 `cmap.json` | `codes` 2304 条；上限 2847，余 543 |
| 术语审计（批次前基线） | 复跑 `python tools/audit_terms.py` | 161 条（P1 10 / P2 96 / P3 55），与 `TERM_AUDIT_REPORT_20261121.md` 一致，可复现 |
| 术语批次（T-10b/T-11/T-12） | 复跑 `audit_terms --date 20261121_r3` + `validate_build` | 161→72（P1 0 / P2 43 / P3 29）；说话人 97→40 组；Z19/Z27 error 0 / warning 46、stable error 0 / warning 1 |

### 2.2 2026-11-13（历史）

| ID | 复核方式 | 结果 |
|---|---|---|
| T-01 | 读 `cmap.json` + 连续两次 `package_current` | 2300 字；第二次 `+0 新字`；哈希一致；2300 码唯一且均可反查 |
| T-02 | 读 `dialogue_issues_status.tsv` | 待核对 0；已修复 427 + 保留原译 2；`import_review` 收到 530 处修订 |
| T-05a | 对照译表、`t17_q16_candidates.tsv` 与 Z19/Z24 产物 | 10 个说明槽被 Q16 误伤；修复后 5 条说明全部上屏；剩 `Large/Heavy Attack`、`Trigger Rate` 未登记 |
| T-05b | 读 Z25 产物 + 对比 Z24 操作数 | Wind 10/10 槽中文；4 个操作数变化；敌技 9 槽中文；validate error 0 / warning 45 |
| T-05c | 读 Z26 产物 + 对比 Z25 操作数 | 47/47 槽中文；操作数 0 变化；validate error 0 / warning 45 |
| T-06 | 读报告 + 查 CSV | `b928/59516`、`b928/67400` 两行确实省略了名字 |
| T-07 | 读新配方 + 检查 dist | Z19 `HMH2_Z23_RELEASE=1`，LANG_EN `fbe38d771f76`；stable `=0`，LANG_EN `cde1b071c2fc`；validate error 0 |
| T-08 | 2026-11-09 `verify_charset_full.py` + 构建输出 | 上屏缺字 0；`row1992` 显示英文原名 |
| T-09 | `git merge --ff-only` + 重建校验 | 28 个提交快进合并成功；Z19/stable/Z24 均从 `main` 重建，validate error 0 |

## 3. 不在此表的项

- **实机测试**：Z19 图鉴/战斗说话人/宝箱、Z25 技能栏、Z26 敌技名、Z27 选项与尾行与队伍界面「副队长亚修」、
  DLC Q78 船、马/摩托/越野车/竹马、Mu/Xi 获取等，见 `docs/FINAL_QA_PLAN.md` §2.1。
- **明确不修**：Q16「勇者城」相关**键名槽**（`KNOWN_ISSUES.md` §4）、`Hero<>` 模板槽、
  `b509/908` 脚本键槽、称号 `b931 pos36`、`b317` 连携技表。
- **既定差异**：stable/E3 不含 4 个视频与 `cscv[355]` 歌词，是配方设计，不是缺漏。

## 4. 已同步的过期文档

**2026-11-21（TODO 重排与术语落地复核）：**
- `docs/TODO.md`：按 P0～P3 重排；合并 T-04a+T-05a→T-04、旧 T-03+T-04b→T-03；
  拆分 T-10 为 T-10b、T-13→T-13a；新增 T-07b（发布基线重建）；
  T-12 修正为「部分完成（Z27）」；补记 `b76af42` 魔法书统一与 Z27 三项；
  修正过期引用（`build_cn.py` 2481→2601、cmap 2300/547→2304/543）；新增旧 ID 对照表。
- `docs/TERM_AUDIT_REPORT_20261121.md`：161 条候选与复跑结果一致。
- `docs/TERM_RECOMMENDATIONS_20261121.md`：145 个唯一术语的推荐译名与术语表修改建议。
- `locales/zh-CN/proofread/term_review_recommendations_20261121.tsv`：机器可读推荐表。
- `tools/audit_terms.py`：只读术语审计脚本；每轮打包后可复跑。

**2026-11-15（T-04b 状态修正 / T-05b、T-05c 完成）：**
- `docs/TODO.md`：T-04b 由“未实施”改为“游戏内显示已完成，剩余校对视图登记”；
  补充 `Villager's Clothes`×2、`Hellfire`×1 两个例外；复核证据同步更新。
- `docs/TODO.md`：T-05b 标记完成（Z25；Wind 10 槽 + 敌技 9 槽，4 个操作数，error 0）。
- `docs/TODO.md`：新增 T-05c 并标记完成（Z26；47 槽 / 44 个敌技显示名，0 操作数，error 0）。

**2026-11-13（T-09 合并）：**
- `docs/TODO.md`：T-09 标记完成（28 提交、合并后三个包重建校验通过）。
- `README.md`：最高优先级指针改为分支已完成合并。
- `docs/PACKAGE_LEDGER.md`：移除「`main` 滞后」提示，补记合并与重建。

**2026-11-12（上一轮）：**
- `docs/TODO.md`：拆分 T-04a/T-04b（假命中 vs 装备名副本）、T-05a/T-05b（纯显示 vs 机制名），补入本轮精确落点。
- `docs/PACKAGE_LEDGER.md`：Q16 修复后的 Z19/Z24/stable 新哈希与变更记录。
- `docs/PITFALLS.md`：新增 Q16 守卫误伤说明文的陷阱记录。
- `docs/KNOWN_ISSUES.md`：§21 说明文状态、§10.3 哈希。
- `BUILDING.md` / `docs/PROOFREAD_DIALOGUE_ROUND2.md`：哈希同步。

**2026-11-09（上一轮）：**
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
