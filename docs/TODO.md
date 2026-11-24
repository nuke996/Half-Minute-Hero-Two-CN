# 未完成项总表（TODO）

> 用途：把**除实机测试以外**的未完成项集中登记，避免散落在 `KNOWN_ISSUES.md`、
> `PACKAGE_LEDGER.md`、`FINAL_QA_PLAN.md` 与项目记忆中。
> 最近复核：2026-11-22（T-14 名词错译审计：批次 1/2 A 组已落地并重建 Z29；
> 批次 3/4 待做。T-03 已完成：歌词/装备名副本接入校对视图并实测回滚）；
> 2026-11-21（T-10b/T-11/T-12/T-13a/T-07b 已落地并重建 Z27/Z19/stable；
> 仅剩 `row 20447` 按钮语义待实机、P3 收尾项与实机测试）。
> 上一轮 2026-11-15：修正 T-04b（游戏内显示已完成，剩余校对视图登记）。
> 2026-11-13：T-09 完成，`proofread` 快进合并入 `main`，后续开发以 `main` 为主分支。
> 实机测试项不在此表：见 `docs/FINAL_QA_PLAN.md` §2.1 / §2.3 / §2.4 与 `docs/PACKAGE_LEDGER.md` §2。

## 1. 待办总表

### 1.1 P0（先做，用户可见的内容/功能错误）

| ID | 类别 | 待办 | 当前状态（2026-11-24） | 建议下一步 | 关联文档 |
|---|---|---|---|---|---|
| **T-17** | 机制/闪退 | `#PARTY` 脚本伙伴名断链：Q73 真・大叔不生成 → 闪退；Q19/Q63 同型 | **Z30 已构建，待逐关实机。** 第一轮 `EXP-Q73-party` 伙伴出现但仍闪退；第二轮 `EXP-Q73-party2`（再修 `#HERO_CATSLEPARTS`）Q73 开场通过。Z30 已把 `#PARTY` 3 处、`#HERO_CATSLEPARTS` 5 处、`b358` Q16 菜单键落地（`LANG_EN 0317ab1be137`，validate error 0 / warning 46）。**Z30 实机：Q73 通过，逐关未发现异常（2026-11-24）。** Z31 已构建但**序章装备丢失（已作废）**：把 `Brave Vest　` 的全角空格当填充剥掉，串到另一道具。Z32 已修正：loadout 只改 Ad Hoc 1–7 的 21 处，序章 `rec0` 与 Z30 逐字节一致，审计 0 问题，`LANG_EN 129ab4ac1030` 待实测 | ① 实测 Z32：序章初始装备（应与 Z30 一致）、Ad Hoc 1–8、DLC 5 称号、`Deprived Male Bird`；② 通过后 Z32 升为发布基线并更新 `PACKAGE_LEDGER` | `PITFALLS.md` §54、`KNOWN_ISSUES.md` §26、`PACKAGE_LEDGER.md` §2/§3 |
| **T-18** | 机制/脚本键审计 | **全库“脚本按名查表”同步审计**：同类问题已出现 4 次（伙伴 `#PARTY`、城堡零件 `#HERO_CATSLEPARTS`、载具 `stride152 pos24`、Q16/`b358` 菜单键），必须做**穷举式**审计，不能靠“已知命令/已知偏移”清单 | **工具已完成并跑出正式结果（2026-11-24）。** `tools/audit_script_name_refs.py`：canon（2612 条/14 类）+ 任意 `#CMD(...)` + 任意 `key=value`（含 `foot2=` 换行写值形态）+ 整槽/嵌入名 + JA 差分 + text_v2 显示白名单 + Q16/操作数；输出 `build/audit/script_name_refs.tsv`。**Z30 结果（修正后）：机制性不同步 26（21 处 b34 Ad Hoc loadout + 5 处 DLC 称号条件副本），未解释松散候选 0，另 1 处 DLC 敌名副本译名不统一。** 早前把 `Brave Vest　`/`Brave Blade　` 的 2 处也算作不同步是误报（见 PITFALLS §54.2）。回归验证：对 Z29 能抓出 8 条 `#PARTY`/`HERO_CATSLEPARTS` + 1 条 `b358` Q16。**Z32 已修复全部 26 处，审计 0 问题、exit 0。** | ① 把审计接入 `validate_build` 门禁（Z32 已 0 error，可接入）；② 加回归夹具（故意回退 `#PARTY`/`HERO_CATSLEPARTS`/`foot2=`/DLC 称号副本/`Brave Vest　` 必须失败） | `PITFALLS.md` §54/§54.1、`TECHNICAL.md` §10.3.13、`PACKAGE_LEDGER.md` §3 |
| **T-19** | 机制/loadout | **`head=/body=/handR=/handL=/foot=` 装备名同步**：脚本 loadout 里的装备名必须等于道具表终串（PITFALLS §25.3） | **Z32 已修复，待实机。** 21 处已定位（修正后审计）：`b34 rec214–220`（Ad Hoc 1–7）各有 `foot2/foot3/foot4` 的**换行写值**形态（`foot2=` 下一行才是 `Academy Boots`/`Resistance Boots`/`Brave Boots`），共 21 处仍是英文；同内容的 `Ad Hoc 8`（rec221）是同行写值、已正确翻译 | ① 新增 `sync_script_loadout_names()`：解析所有 `key=value`，**支持值在下一行的形态**，按 `b147/357/736/998` canon 写回；② `validate_build` 增加 loadout 一致性检查（含换行值）；③ Z32 已重建；实机确认 Ad Hoc 预设（序章 rec0 与 Z30 逐字节一致） | `PITFALLS.md` §25.3/§54.1、`TECHNICAL.md` §10.3.13、`PACKAGE_LEDGER.md` §3、`KNOWN_ISSUES.md` §27 |
| **T-20** | 机制/称号键 | **DLC01 名字副本同步**：DLC 的 `stride292 pos32` 是称号取得条件/进度副本；原版 JA 里它与主称号表 `b931 pos0` 逐字节相同。DLC 管线独立翻译后与主表终串不同 → 按名条件匹配失败，称号无法取得 | **Z31/Z32 已实现，待实机（主表改用 DLC 措辞）。** 5 处已定位（2026-11-24 正式审计）：`It was the Breeze`（DLC 掀裙全制霸 vs 主表 全翻篇了）、`Nothing Dirty`（不许色色 vs 不许搞黄）、`Turn the Tables`（反杀 vs 反杀回去）、`Ruler of the World!`（夺取天下！vs 天下霸主！）、`Construction Stopper`（不许筑城 vs 阻止筑城）。另 `DLC01 b7 rec323 pos96` 的敌名/说话人名副本 `Deprived Male Bird` 译作「缺爱公鸟」，主表为「饥饿公鸟」（译名不统一） | ① 在 `refresh_dlc01` 之后对 `DLC01/LANG_EN` 复用主表 canon：DLC 版 `force_title_key_copies`（stride292 pos32）+ 敌名/说话人名副本统一；② 审计接入门禁后此 6 处必须为 0；③ Z32 已重建；实机确认 DLC 称号可获得、敌名一致 | `PITFALLS.md` §25.17/§54.1、`TECHNICAL.md` §10.3.13、`KNOWN_ISSUES.md` §28 |

### 1.2 P1（发布前必须处理）

| ID | 类别 | 待办 | 当前状态（2026-11-21 复核） | 建议下一步 | 关联文档 |
|---|---|---|---|---|---|
| **T-13a** | 术语表/方向拍板 | 术语表按推荐表定向；确认阻塞项方向 | **已完成（2026-11-21）**。术语表已按推荐表定向：`おじさま→大叔`、`銃士→火枪手`、`ウォーリア→勇士`、`エクスペリダイブ→经验俯冲`、`登場セリフ→出场台词`、`アイテム→道具`、`悪ガキ→小鬼`；`魔王ケルベロス→刻耳柏洛斯`、`テント→帐篷`、`歌族`、`海岸人鱼`、`黄金冲击`、`赞特赫尔`、`辛多尼克斯`、`贝塔`、`红萝卜老爷` 均已落表。`アヴァ`/`スペルヴィア` 因 EN 槽位仅 3/7 字节回退为「艾」/「斯佩维」（§13） | 无；新增术语先按 §13 做容量评估，再进术语表 | `TERM_RECOMMENDATIONS_20261121.md` §5、`术语表.md` §3–§13、`tools/audit_terms.py` |
| **T-10b** | 术语/误译/漏译 | 第一批高置信误译与漏译（原 T-10 主体 + T-06 漏名 + T-05c 遗留） | **已完成（2026-11-21 Z27），1 项待实机**。① `船頭` 13/13→船夫；③ `extra::417::206540`→超新流星；④ `row::6113`→火枪手、`row::10938`→魔法师之路；⑤ `おじさま` 47 处（CSV 39 + extra 1 + DLC 7）→大叔，`火枪手` 全表 7；⑥ `row::53227/53228/53242/53243` 超土おとこ 四行重排，统一为「超级泥浆怪/超级泥浆王」；⑦ `Hellfire`/`Dogry`/`Reusable` 在译表 0 命中（仅二进制副本，非显示串），`Venus Seven` 仅首次括注，登记例外。② `row 20447` 日文 `キャンセル` / 英文 `Continue`，暂保留「继续」 | 实机确认 `row 20447` 暂停菜单按钮语义；若确认为 Continue 则登记例外，否则改「取消」 | `TERM_RECOMMENDATIONS_20261121.md` §2.1/§6、`KNOWN_ISSUES.md` §21 |
| **T-14** | 术语/名词错译 | 校对名词错译（英文多义词 + 日文片假名） | **批次 1/2 A 组已完成（2026-11-22 Z29）**：`封印の獣→封印兽`；`Demon Spawn/Chompers/Bolt/ゲニン/ジョウニン/ウニエル/Pegielle/Masosnail/Sadosnail/Erosbster/どろたぼう/Deprived Male Bird/Hornmoomoo/Fortify` 等 16 组敌名已改并同步全部副本。`validate_build` error 0 / warning 46，旧串 0 残留；产物 `LANG_EN 69946916d971`。**批次 3/4 待做**：装备名 `Hero Cloth/Bastard Sword/Fossil Away/Bent Sword/Angel's Ring/Charisma Wig/Royale·Crimson Guard`；称号/一致性 `Dragon Header/Evil Lord Medal/Sage's Staff/Angel Shell/Virtual Castle`。B 组 `Ribbit/Forbidden Gem/Sacriphys Village` 等待拍板 | 先做批次 3（`Bastard Sword` 已拍板「混种大剑」；`Hero Cloth` 与 `Hero Cross` 共用日文串，需小包验证）；再做批次 4；B 组逐项确认后并入 | `docs/NOUN_AUDIT_20261122.md`、`术语表.md` §5/§8、`PACKAGE_LEDGER.md` §6 |
| **T-07b** | 发布工程 | 重建 Z19 / stable 发布基线，并入 Z25–Z27 与术语批次 | **已完成（2026-11-21，工作树 dirty）**。Z19 `LANG_EN 1b0109baf96a` / texture `fb5b79e17e37` / cscv `f074004c8eb3` / DLC01 `bbe1e4a87b61` / MOV `237ee86d26f6`；stable `LANG_EN 155e2b3784b9` / cscv `8f0bd9db2a40` / DLC01 `d139508e35c0`；Z27 与 Z19 内容一致。validate：Z19/Z27 error 0 / warning 46（+1 为「对话设置」同串），stable error 0 / warning 1。`build_manifest` 均为 git `a642734 (dirty)` | 提交后从干净 `main` 复跑一次以消除 manifest 的 dirty 标记；实机验证 Z19 后替换发布包 | `PACKAGE_LEDGER.md` §2/§5、`BUILDING.md` §5.5 |
| **T-15** | 发布工程/闪退 | `dist/stable-names-en` 主界面闪退定位 | **Investigating（2026-11-22，实机已缩小）**。English 必崩；同一包切日本語可正常进入且字形正常；闪退在读档页之前 ⇒ 排除语言前置、字体图集与存档。问题限定在 `LANG_EN` 启动期数据。首要怀疑 E3 的显示放行/副本同步与当前 Z22–Z29 译表不同步，造成菜单项名与分组标签混合态（§9/§23 同类） | 生成 stable vs Z29 的 LANG_EN 逐槽差异，筛 `b25/b186/b280/b354/b358/b410/b534/b763` 的菜单/消息槽，找“单边已译”的成对项；再做最小实验包 | `KNOWN_ISSUES.md` §24 |

### 1.3 P2（发布前建议处理）

| ID | 类别 | 待办 | 当前状态（2026-11-21 复核） | 建议下一步 | 关联文档 |
|---|---|---|---|---|---|
| **T-11** | 术语/专名统一 | 术语表 §12 与专名批量统一 | **已完成（2026-11-21 Z27）**。`歌之族`/`陆地鱼人`/`陆鱼人`/`淘金热`/`瑟伯勒斯`/`赞特地狱`/`辛多尼斯`/`红萝卜老伯`/`坏小子` 全部归零；`歌族`、`海岸人鱼`、`海岸人鱼姐妹`、`黄金冲击`（含复合槽 7966/7988）、`刻耳柏洛斯`、`赞特赫尔`、`辛多尼克斯`、`贝塔`、`红萝卜老爷` 已统一。`アヴァ` 保留「艾」、`スペルヴィア` 保留「斯佩维」：EN 槽位仅 3/7 字节，长形式会触发名字一致性校验 error（见 §13/PITFALLS） | 无；后续新增专名先查 §13 容量 | `TERM_RECOMMENDATIONS_20261121.md` §2.1/§2.2、`术语表.md` §12、`term_review_recommendations_20261121.tsv` |
| **T-12** | 术语/说话人标签 | 说话人标签统一（97 组） | **已完成主体（2026-11-21 Z27）**。97 组降至 40 组；`副隊長ヤーシュ→副队长亚修` 已统一；专有人名、店铺标签、泛称人物按推荐表批量处理。剩余 40 组均为 `保留差异`（主人/おやじ/店主/老人/おばさん/学者/マスター/おじさん/めしや 等）或按语境差异；`巻物`/`ババ` 误报未动 | 剩余为设计上的语境差异，不再批量替换；新增说话人先按推荐表 §3/§4 判断 | `speaker_label_variants_20261121.tsv`、`TERM_RECOMMENDATIONS_20261121.md` §3/§4 |
| **T-16** | 机制/野外演出 | Q16 前世界地图「巨型果冻怪」不显示 | **已完成（2026-11-22）**。根因：`text_v2.csv` row 10494（b176 off441816）把二进制 `46 87 85`（`F㊤`）写成 `F`，清零 `87 85`；row 56515（b974 off134632）同类。已删除 7 条二进制误判行、加 `binary_slot` 守卫，重建 Z29（`LANG_EN 7a50785f8b12`，error 0 / warning 46），translator-view 已刷新；实机确认果冻怪恢复 | 无 | `KNOWN_ISSUES.md` §25、`PITFALLS.md` §48 |

### 1.4 P3（收尾项，不影响发布）

| ID | 类别 | 待办 | 当前状态（2026-11-21 复核） | 建议下一步 | 关联文档 |
|---|---|---|---|---|---|
| **T-04** | 放行/未登记表 | 纯显示串与 collide 假命中放行（原 T-04a + T-05a） | **部分完成（2026-11-22 定性）**。已完成 11 个 collide 放行（b906 记忆检查、b34 关卡名、b186、b282、b757、b905）。剩余 4 项定性：① `b630` `You took damage!`（LANG_EN off4750，JA `ダメージをうけた！`）命中 cscv b23/596/881 战斗消息表 → **假命中**，可放行 1 槽并新增译行；② `b845` 影片/结局曲名 7 条（off 88/292/496/700/904/1108/1312）命中 cscv b814 同位置同名表 → **假命中**，须整表 7 条一起放行+翻译，否则半中半英；③ `b357 off122396/122664` `Large Attack`/`Heavy Attack` = Blade/Saber 的 `+168` 技能名列（pos172），全库仅 2 处、cscv 0 命中、无操作数 → **纯显示装备技能名，可译**；④ `b666 pos160` `Trigger Rate: 1/x` 86 槽 / 18 种，cscv 0 命中，已在“说明文放行”规则内 → **纯显示 UI 文案，可直接登记译行**（建议「发动率 1/10」）。另：`b320` 的 `Grand Ending` 2 行未受保护但仍是英文（普通漏译），可与 b845 一并处理 | 按上述定性分两批：先放行 b630/b845 并补译行（需重建 Z27/Z19）；b357/b666 只补译行。建议译文：`受到伤害！`、`序章`/`OVERTURE 片头`/`OVERTURE 片尾`/`JUDGEMENT 片尾`/`REVOLUTION 片尾`/`RAGNAROK 片尾`/`大结局`、`强力攻击`/`重攻击`、`发动率 1/x` | `KNOWN_ISSUES.md` §12、`PACKAGE_LEDGER.md` §5 |
| **T-08** | 已知取舍/演出 | 生僻字回退与 RAGNAROK 字幕同步 | **半开放**。2026-11-09 实测上屏缺字 0；`cmap.json` 现为 **2304/2847（余 543）**；制作人员 `row1992` 的「崇」回退英文名；RAGNAROK 字幕仍略早于音频 | 生僻字按需扩容或接受现状；RAGNAROK 若处理，优先评估运行时字幕叠加方案 | `KNOWN_ISSUES.md` §7/§20、`tools/verify_charset_full.py` |

### 1.5 已完成（保留记录）

| ID | 完成时间 | 结果 | 关联文档 |
|---|---|---|---|
| **T-01** | 2026-11-09 | 载体码（cmap）固化，`locales/zh-CN/cmap.json` 为 append-only；连续构建 `+0 新字`，哈希一致 | `KNOWN_ISSUES.md` §13、`PITFALLS.md` §27 |
| **T-02** | 2026-11-09 | 导入对话校对 429 条清零（427 修复 + 2 保留原译，529 槽）；Z24 重建 error 0 / warning 45 | `PROOFREAD_DIALOGUE_ROUND2.md` |
| **T-05b** | 2026-11-15（Z25） | Wind 两技能 10 槽 + 敌技显示名 9 槽中文化；仅 4 个操作数变化；validate error 0 / warning 45 | `dist/Z25-mech-names/`、`KNOWN_ISSUES.md` §21 |
| **T-05c** | 2026-11-15（Z26） | 47 槽 / 44 个敌技显示名；操作数 0 变化；cmap +4（2304）。**遗留项已转入 T-10b**：`Hellfire`、`Venus Seven`、`Dogry`、`Reusable` | `dist/Z26-enemy-skills/` |
| **T-07** | 2026-11-09（2026-11-12 重建） | Z22–Z24 并入 Z19/stable；仅 Z19 放行敌名/Boss 图鉴名。**发布基线后续更新见 T-07b** | `PACKAGE_LEDGER.md` §2/§5 |
| **T-09** | 2026-11-13 | `proofread` 28 个提交快进合并入 `main`；三个包从 `main` 重建校验通过 | `PACKAGE_LEDGER.md` §6 |
| 术语清理（无独立 ID） | 2026-11-21 | 提交 `b76af42` 统一 `グリモワール/グリモ→魔法书`，`魔典/格瑞莫/格里莫` 在 `zh_new` 已归零；Z27 完成 27 个选项放行、15 个尾行留空、副队长统一（术语批次重建后 `validate_build` error 0 / warning 46） | `docs/TEMP_REVIEW_20261121.md`、`PACKAGE_LEDGER.md` §2 |
| **T-10b/T-11/T-12/T-13a/T-07b** | 2026-11-21（Z27/Z19/stable） | `船頭/おじさま/銃士/魔道士/悪ガキ/超新流星` 等第一批误译落地；专名与说话人标签批量统一（97→40 组）；`audit_terms` 161→72（P1 0）。重建 Z19/stable/Z27：validate error 0，warning Z19/Z27 46、stable 1；哈希见 `PACKAGE_LEDGER` §2 | `docs/TERM_RECOMMENDATIONS_20261121.md`、`术语表.md`、`PACKAGE_LEDGER.md` §2 |
| **T-03** | 2026-11-22（Z27 重建） | 非 CSV 表接入校对视图：新增 `60_songs.json`（28 条歌词）→ 导入写 `locales/zh-CN/song_en_lines.json`，`song_lines()` 覆盖内置表；装备/道具名副本（`EQUIP_BLOBS pos4` 同名、位于其他 blob）在视图标注 `meta.canonical`，导入写回权威行；无独立译表行的参数串/机制名副本导出到 `protected/prot_itemcopies.json`（150 条，含 `Villager's Clothes`×2、`Hellfire`×7 副本），导入跳过。实测歌曲 k=2 与副本改 `row::7736` 均写入 dist，回滚后 `LANG_EN 1b0109baf96a` / `cscv f074004c8eb3` 恢复，validate error 0 / warning 46 | `PITFALLS.md` §38、`BUILDING.md` §5.4、`PACKAGE_LEDGER.md` §5/§6 |
| 术语批次（Grimoire 音译） | 2026-11-23（Z29） | 故事/UI 显示文本：`グリモワール→格瑞莫瓦尔`、`グリモ→格瑞莫`（102 行 CSV + 8 条多行），昵称 `<小典>/<魔法书>→<小莫>`；武器道具 `row::7402` 及 20 个名称/说明副本、获得提示 `row::34043`、图鉴说明 `ml::804` 保持「魔法书」；机制名 `row::32917`（脚本标识）与 `row::53626/53629`（称号表章节副本）、4 条英文 BGM 曲名保留。新增 `tools/fix_terms_grimoire.py`；重建 Z29，validate 结果见 `PACKAGE_LEDGER.md` | `术语表.md` §1/§8/§13.1、`PITFALLS.md` §50、`PACKAGE_LEDGER.md` |

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
| T-03（实施后） | `export_review.py` + `import_review.py apply`/`revert` | 导出 28 条歌词、150 条副本登记、7016 条副本 `meta.canonical`；改 k=2 与 `row::7736` 后重建，`cscv[355]` 反解码一致、`row::7736` 写入权威行；回滚恢复 `LANG_EN 1b0109baf96a`/`cscv f074004c8eb3`；validate error 0 / warning 46 |
| T-08 | 读 `cmap.json` | `codes` 2304 条；上限 2847，余 543 |
| 术语审计（批次前基线） | 复跑 `python tools/audit_terms.py` | 161 条（P1 10 / P2 96 / P3 55），与 `TERM_AUDIT_REPORT_20261121.md` 一致，可复现 |
| 术语批次（T-10b/T-11/T-12） | 复跑 `audit_terms --date 20261121_r3` + `validate_build` | 161→72（P1 0 / P2 43 / P3 29）；说话人 97→40 组；Z19/Z27 error 0 / warning 46、stable error 0 / warning 1 |
| **T-14（2026-11-22）** | 读 `text_v2.csv` / `ml_zh_fields.json` + 构建 Z29 + `validate_build` + 产物字节计数 | 批次 1/2 A 组共 16 组敌名/1 条图鉴已落地；`LANG_EN 69946916d971`，validate error 0 / warning 46；旧译序列 0 残留；字体覆盖 100.07% |

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

**2026-11-22（T-14 名词错译批次 1/2）：**
- 新增 `docs/NOUN_AUDIT_20261122.md`：完整 A/B 表、批次 3/4 计划、B 组待拍板项。
- `术语表.md` §5：补入本批 16 组敌名/`封印兽`；§8 登记 `バスタードソード→混种大剑`（待批次 3）。
- `docs/TODO.md`：新增 T-14 并定为 **P1**（与 T-10b 同属发布前必须处理的误译；
  P0 当前无功能阻塞项；批次 3 的装备名用户可见，故不能降为 P2/P3）。

**2026-11-22（T-03 完成）：**
- `docs/TODO.md`：T-03 从 P3 移入已完成；补实施与回滚证据。
- `BUILDING.md` §5.4：导出/导入清单加入 `60_songs.json`、`song_en_lines.json`、
  `protected/prot_itemcopies.json` 与 `meta.canonical` 重定向说明。
- `docs/PITFALLS.md` §38：歌词「未做（有意）」改为已接入校对通道，并记录副本登记口径。
- `docs/PACKAGE_LEDGER.md` §5/§6：同步本轮通道与哈希。

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
