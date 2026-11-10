# 已知问题（KNOWN_ISSUES.md）

本文档记录**玩家可见**的已知限制、未完成区域与兼容问题。

> 状态枚举：Open / Investigating / Workaround available / Partially fixed / Fixed in development /
> Fixed in release / Won't fix / Upstream issue / Version-specific。
> 严重度：Critical / High / Medium / Low / Cosmetic。

---

# 0. 先说清楚：大量"未翻译"是**刻意保留**，不是漏翻

**Status:** Won't fix（设计使然）　**Severity:** Cosmetic（对老玩家）/ Low

游戏存在"按字符串内容比对"的机制，某些文本（人物名/敌人名/魔王名/神名/技能名/道具装备名/章节名等）
是运行时查找的键。为保护机制，构建用碰撞白名单（collide）**刻意保留原文**。

- 最近一次报告口径：刻意保留约 **27,044 处 / 5,042 种**串。
- 因此"某处仍是日文/英文"**通常不是漏翻**，而是保护结果。
- 判断方法：见 `TECHNICAL.md` §5.3 与 `TRANSLATING.md` §11。

---

# 1. 名字类中文化（分批推进，仍有保留原文项）

**Status:** Partially fixed（2026-11-05）　**Severity:** Low（可见性）
**Affected locales:** zh-CN

**症状：** 部分名字类（称号/伙伴/职业/阵形/装备/技能/敌人等）在部分位置仍显示日文（英文模式显示英文）。
**技术说明：**
- 历史两次实锤（露露菲实验、测试 E）后曾得出"名字保留原文定局"；
- 2026-09-18 起改用"仅写 LANG + 同一语言文件内全副本同改 + cscv 全保日文 + 账本回滚"的方法，
  实验 D/E 出现反证（武器技恢复触发），并已分批实施（账本 24 批 / 44,129 槽）；
- 但同日的两份评估文件结论相互冲突，**最终以实机验证为准**。
**Workaround：** 通过 `python tools/t140_name_revert.py revert <批次id>` 可退回任意批次。
**当前状态（2026-11-05，Z24）：** 技能/装备名（Z10b）、伙伴名（Z11）、敌名/Boss 名（Z12 说话人 +
Z23 图鉴列表 + Z24 跨表专名统一）、职业/阵型/称号（Z14）、`Mu`/`Xi`（Z18）已中文化；
仍按守卫保留原版的有 `b317` 连携技表、Q16 记录、`b931 pos36` 章节标题副本与部分敌技名
（见 `docs/PACKAGE_LEDGER.md` §3/§7、`docs/TODO.md` T-05）。
**相关文件：** `TECHNICAL.md` §8、`locales/zh-CN/name_ledger.json`、
历史报告 `名字类全量中文化可行性评估-20260918.md`、`键值同改历史复核与本轮结论修正-20260918.md`（未随仓库分发）。

---

# 2. 剧本对话误译（TODO-5，最大未完成项）

**Status:** Fixed in development（2026-11-09：待核对清零）　**Severity:** Medium（翻译质量）
**Affected versions:** 当前装机全部版本　**Affected locales:** zh-CN

**症状：** 部分对话译文与日文原文含义不符（如 `Thank you so much`、`Discussion over.`、
`My control is waning` 一类被英文本二次创作改写）。
**触发：** 剧情/支线对话。
**实际原因：** 主译表以 **3DM 补丁**为底本，3DM 又以**英文本**为底本；英文版本身存在失真。
**影响范围（已评估）：** 对话表族真句子台词槽约 **21,376 槽**（F292 16,012 / F424 3,329 / F196 2,035），
覆盖 **724 个 blob**。
**Workaround：** 无需；第二轮校对已完成。
**Technical notes：** 2026-10-29/30 导入 **1821 单元 / 2842 处条目**（产物 `dist/Z19-proofread/`）；
2026-11-09 把最后 **429 条待核对**全部落实（**427 条已修复 + 2 条保留原译**，共改动 **529 处槽位**（另有 1 处既有人工修改，导入合计 530 处）），
逐条原文/原译文/现译文见 `docs/PROOFREAD_DIALOGUE_ROUND2.md`；`dialogue_issues_status.tsv`
剩余待核对 **0**。Z24 重建 error 0 / warning 45。
**相关文件：** 历史报告 `TODO-待办清单.md`、`TODO5-*.md`（未随仓库分发）；
`locales/zh-CN/proofread/dialogue_issues_status.tsv`、`docs/PROOFREAD_DIALOGUE_ROUND2.md`。


---

# 3. 敌人名与敌人专用招式名

**Status:** Partially fixed（2026-11-04，Z23：图鉴列表名已上屏，待实机）　**Severity:** Low
**Affected locales:** zh-CN

**症状：** 敌人名（图鉴/战斗/招募提示）与敌人专用招式名在游戏中仍为原文。
**技术说明：**
- 敌人名约 700 名 / 约 7,660 副本（官方 EN 100% 改过 => 可翻）；图鉴名集 104 + 敌数据名集 ~600。
- 敌人专用招式仅约 5 个；其余走玩家技能表。
- 教训：技能/名字跨表按名关联，须"EXACT 全副本同改"，并**先做键名列排查**再动手。

**当前进度（2026-11-09）：** 图鉴**列表主名列**已放行上屏：怪物页 `b734 +40`（138 条）、
头目页 **`b555 +40`（107 条）**，以及同名副本 `b54 +40`、`b105`/`b529 +92`
（`Hero<>` 模板槽与 `b509/908` 脚本键槽保留原版）。2026-11-09 T-07 决策：**发布基线 Z19 启用
`HMH2_Z23_RELEASE`**（与 Z24 同哈希），stable/E3 仍保留敌名原文作为安全回滚包。
构建自检 error 0 / warning 45，字形级反查逐字正确；**实机需验图鉴两页、战斗说话人、招募/宝箱**。
见 `docs/PITFALLS.md` §42、`docs/PACKAGE_LEDGER.md`（Z23）；Z24 另完成 91 行跨表专名统一
（见 `docs/PROOFREAD_NAME_REPORT.md` §10），两版均待实机。
**相关文件：** 历史报告 `敌人名与敌人技能名-可翻译性评估.md`（未随仓库分发）。

---

# 4. Q16 相关台词仍为原文

**Status:** Won't fix（已知可见代价）　**Severity:** Low
**Affected locales:** zh-CN / en（按语言显示各自原文）

**症状：** 含"勇者城"的约十几行台词（`196/28`，日文侧 14 + 英文侧 14 处）保持原文。
**技术说明：** 这些串同时是"按键名查找"的标识，必须保留（`restore_q16_keys()`）。
   这是修复"勇者城消失"的必要代价，不是故障。
**相关文件：** 历史报告 `Q16勇者城-第二版根因与修复-20260918.md`（未随仓库分发）。

---

# 5. 制作人员 / 版权页姓名的字形差异（历史代价）

**Status:** Fixed in development（v2.14 起恢复原版字形）
**Severity:** Low

**说明：** v2.7 曾回收 index 1024–1119 的版权/制作人员姓名汉字区以扩格，
代价是版权页日文姓名显示为汉字乱码。**v2.14 起不再回收原版 index 0-1247**，该代价已消除。
**注意：** 若回退到旧策略（`RECLAIM_STAFF=True`）会重新出现此问题。
**Z15 补充（2026-10-22）：** 同字复用只重画 `256..1023` 中与译文同码位的 523 个汉字格，
STAFF 区 `1024..1119` 本身未回收。版权页姓名若含这 523 个字，会显示**同字的简中字形**
（码位/字符身份不变，不是乱码）；这是有意换取字库容量的外观取舍。

---

# 6. 少量 UI 标签仍为原文

**Status:** Fixed in development（生产配方默认启用 `ui_always=True`）　**Severity:** Low
**Affected locales:** zh-CN

**症状：** 个别纯 UI 标签/提示（如 `はなす`/交谈、`女神像ワープ`/女神像传送等 14 串）仍为原文。
**技术说明（2026-11-06 复核）：** `locales/zh-CN/ui_always.json` 的纯 UI 串放行已并入生产配方
（Z17 起 `ui_always=True`）；仍显示原文的串多属 collide/键名/Q16 保护，见 §0/§4/§12。
**Workaround：** 无需额外 bat；临时关闭时把配方参数改为 `ui_always=False`。
**相关文件：** `locales/zh-CN/ui_always.json`、`tools/build_cn.py`（`load_ui_always`）、
历史报告 `未翻译文本排查报告.md`（未随仓库分发）。

---

# 7. 极端生僻字可能显示 `?`

**Status:** Accepted limitation（上屏缺字 0；个别生僻字回退英文/`?`）　**Severity:** Cosmetic
**Affected locales:** zh-CN

**症状：** 极少数生僻字显示 `?`。
**技术说明（2026-11-09 实测）：** 图集新字形上限 2847 格；当前 `build_plan()` 新字形 **2300 格（余 547）**，
`cmap` 合计 **2820 字**（含同字复用 520，占原版汉字格 524）；`tools/verify_charset_full.py`
口径 A（真实上屏）**缺字 0**。未覆盖字仍会回退 `?`。
**已知个例：** 制作人员名 `row1992`（"小城崇志"）的"崇"不在 `cmap`/native，`display_text` 保留英文原名
（`Takashi Kojo`），属已知取舍。
**相关文件：** `tools/verify_charset_full.py`、历史报告 `减少问号-方案评估.md`（未随仓库分发）。

---

# 8. Steam 完整性校验会还原汉化

**Status:** Version-specific（预期行为）　**Severity:** Medium
**Affected platforms:** Steam

**症状：** Steam"验证游戏文件完整性"后，被改的 `HMH2.exe` / `res/*.s2a` 被还原，汉化消失。
**Workaround：** 校验后重跑 `汉化-安装.bat`。
**技术说明：** 运行时方案（`dinput8.dll`）可避免改动磁盘 exe，但资源文件仍会被校验还原。

---

# 9. 游戏更新可能导致补丁失效

**Status:** Version-specific　**Severity:** High（若发生）
**Affected versions:** 非当前基准版本

**症状：** Steam 更新后，exe 补丁地址/期望字节可能不匹配，构建中止或异常。
**技术说明：** 补丁工具会校验原字节并在不匹配时中止（不静默），但 `res/*.s2a` 的散列校验尚缺。
**Workaround：** 等待适配；或在支持版本上使用。
**相关文件：** `BUILDING.md` §1、`TECHNICAL.md` §1.1。

---

# 10. 名字类改动属"隐蔽型"风险

**Status:** Investigating　**Severity:** Medium

**症状：** 名字类改动出错时**不会闪退、不会消失**，而是"某技能放不出来 / 某称号拿不到 /
某同伴不能攻击"，玩家不易立刻发现。
**技术说明：** 见 `PITFALLS.md` §5/§6/§7/§11/§25、`TECHNICAL.md` §10.3。
**缓解：** 每次装机后跑 `t34_health.py` 体检 + `t162` 差异审计；实机抽检技能/称号/同伴攻击。

**补充（2026-10-19）：** 已确认根因是**名称 → CRC-32 哈希查表**，
因此"译名重名"与"副本不同步"都会造成静默串味/失效；详见 `TECHNICAL.md` §10.3。

---

# 10.1 当前可用发行包与已知缺陷（2026-10-19，历史快照；现状见 §10.3）

> **已被 §10.2 取代（2026-10-21）：** 机制名/伙伴名中文化已在 Z10b–Z12 实测可行；
> 本节旧结论（“机制名必须保持原版”）仅作为历史记录保留。

| 包 | 构建命令 | 名字语言 | 状态 |
|---|---|---|---|
| **E3**（推荐正式版） | `python tools/build.py --game-dir work/original package_lang_en_names_en` | 技能/装备/伙伴名**英文**，其余中文 | **功能全部正常**；只写 `LANG_EN`，隔离最干净 |
| **HEAD-package**（默认配方） | `python tools/build.py --game-dir work/original package` | 同上（机制名保持原版） | **功能全部正常**；双侧写入 + `cscv` 改写，默认打包行为即此配方 |
| **E3-JA**（E3 的日语镜像） | `python tools/build.py --game-dir work/original package_lang_ja_names_ja` | 同上，但只写 `LANG_JA` | 结构核验通过；**尚未实机回归** |
| **Z4**（中文名可玩版） | `python tools/build.py --game-dir work/original package_names_cn_skill_loadout` | 技能/装备名**中文** | 可正常游玩，但有两个**纯演出**缺陷（见下），**不建议作为默认发布** |
| **Z4-JA** | `python tools/build.py --game-dir work/original package_names_cn_skill_loadout_ja` | 技能/装备名**中文**（只写 `LANG_JA`） | **实机：与 Z4 同样异常** ⇒ 与语言路径无关 |
| **Z6**（单变量对照） | `python tools/build.py --game-dir work/original package_names_cn_skill_only2` | 仅**技能名中文**，装备名英文 | **实机：同样异常** ⇒ 技能名中文化也会触发 |

**Z4 / Z6 的共同缺陷（不影响通关，但确实是 bug）：**
1. 序章伙伴「骑士」死亡演出中**骑士不出现**、复活后**不归队**、**贤者复活特效缺失**；
2. **魔王技能特效缺失**。

**结论（`TECHNICAL.md` §10.3.6、`PITFALLS.md` §25.9）：**
- 只要**任一机制名（装备名或技能名）中文化**，就会出现上述瑕疵；
- 该瑕疵与语言路径（EN/JA）、`cscv` 是否改写、loadout 是否同步**无关**；
- ⇒ **机制名必须保持原版**；对白/UI/说明/消息可以安全中文化。

> E3 与 HEAD-package 均应作为"保证能玩"的版本保留；Z4/Z6/Z4-JA 仅作后续探索的对照包。
> 产物位置：`dist/E3-lang-en-names-en`、`dist/HEAD-package`、`dist/Z4-skill-loadout`、`dist/Z6-skill-only2`。

---

## 10.2 当前实验包状态（2026-10-21，历史快照；现状见 §10.3）

完整的包谱系、症状定位表和回滚命令见 **`docs/PACKAGE_LEDGER.md`**。

| 包 | 产物 | 实机状态 |
|---|---|---|
| **stable**（E3 配方） | `dist/stable-names-en/` | 稳定基准；名字/称号保持原版 |
| **Z10b** | `dist/Z10b-mech-names/` | 技能/装备名中文；序章五项、技能、装备、商店正常 |
| **Z11** | `dist/Z11-partner-names/` | Z10b + 伙伴名/复合键；已测项无问题 |
| **Z12** | `dist/Z12-display-names/` | Z11 + 敌名/Boss 说话人/宝箱/音乐/地图 UI；已测项正常 |
| **Z13** | `dist/Z13-batchB/` | Z12 + 批次 B（技能名/合成 UI）；已测正常 |
| **Z14** | `dist/Z14-jobs-titles/` | Z13 + 职业名/阵型名/称号名 + 新敌技名；**尚未完整实机测试**（历史包，后续由 Z15→Z19 覆盖） |

**Z14 测试状态（2026-10-21）：** 只完成生成与离机校验（职业 12/12、阵型 11/11、
称号 252/252、pos32 460 副本一致、Q16 存疑 0、操作数 242 点 0 失败）。
职业切换、阵型效果、称号获得、Q16 勇者城、Chaos Wing 等仍需实机逐项验证；
出问题优先回滚到 Z13。

**校对支持：** translator-view 现包含今日新上屏文本；非 CSV 的伙伴名/技能名/合成 UI
导出为 `50_extra.json`，导入写入 `locales/zh-CN/extra_review.json` 并固定重建 Z14。
详见 `docs/PACKAGE_LEDGER.md` §9。

**称号中文化（2026-10-21，Z14，待复测）：** 称号名并不是“只能保留原文”——
除 `b931 pos0` 外，各称号条件表还有 `stride292/pos32` 副本；只翻 b931 会造成
按名不可获得。Z14 同时翻译 b931 pos0 与全部 pos32 副本（460 处一致），
并保留 Q16 槽位原字节，离机验证通过。**请实机确认称号列表为中文且可正常获得。**

**已知少量漏译（正式版前统一收尾）：**
- 道具收藏列表：`Mu` / `Xi` 等少数名称（2026-10-21 截图）；
- 怪物图鉴第 1 项 `Jelly`；
- 地图编辑器 `Explanation` 栏说明文字（中英混排）；
- 武器合成界面：`b99 off16` `Wooden Sword +1`、`off56` 说明第一行、
  `b25` `Materials: %s　＋　%s` **未登记进译表**（不是守卫/未放行）。

**职业/阵型/连携技名字泄漏（已修复，待复测）：** 修复前 `fill_name_copies` 未跳过
`skip_blobs(128,136,317)`，导致职业 `Hero`、阵型 `Speed Eater`、`b317` 连携技伙伴名
被部分翻中文。现已跳过这些键表并重建 Z11/Z12；名字列恢复原版，描述列仍按
`desc_release` 正常翻译。

**未测试：** 地图编辑器机制、宝箱名称显示位置、称号重新获取。

---

# 10.3 当前包状态（2026-11-06）

| 包 | 产物 | 状态 |
|---|---|---|
| **Z15** | `dist/Z15-reuse-kanji/` | 回滚基线；龙 NPC、性感泳衣已实机恢复；DLC 船待复测 |
| **Z17** | `dist/Z17-display-fill/` | 显示文本补全 + 4 个视频；音乐播放器购买列表闪退已修 |
| **Z18** | `dist/Z18-dlc-place-names/` | 10-27 快照；DLC 战国地名 + 截图校对轮；**不含 cscv 歌词** |
| **Z19** | `dist/Z19-proofread/` | **当前发布基线**（2026-11-09 重建）：含第二轮对话校对（待核对清零）、`cscv[355]` 歌词、4 个视频；**已并入 Z22/Z24 译文并启用 Z23 敌名/Boss 图鉴列表名**；`LANG_EN eb4bb2263f56`，自检 error 0 / warning 45 |
| **Z20** | `dist/Z20-desc-dodge/` | 实验：道具说明避字（验证"描述渲染器按码错位"）；构建于歌词修复前，**不含歌词**，不作发布基线 |
| **Z21** | `dist/Z21-desc-5f-fix/` | 描述 0x5F 尾字节修复；**2026-11-04 实机通过**，修复已并入 Z19/stable |
| **Z22** | `dist/Z22-ui-lowrisk/` | 低风险 UI 补译批（298 行）；已随译表进入 Z19/stable；未实机 |
| **Z23** | `dist/Z23-ui-mediumrisk/` | 图鉴敌人/Boss 列表名放行 + 「事件道具」；Z19 已启用；未实机（中风险） |
| **Z24** | `dist/Z24-mapeditor/` | 地图编辑器「说明」重译 + 91 行跨表专名统一；未实机；**当前导入校对目标**（`CURRENT_REVIEW_RECIPE=z24`）；2026-11-09 重建 `LANG_EN eb4bb2263f56`，error 0 / warning 45 |

> **stable / E3（2026-11-09）：** 已按当前译表重建（`LANG_EN 2f7dae57bc10`，error 0 / warning 1），
> 但按 T-07 决策**继续保留敌名/Boss 图鉴列表名原文**，作为未实机验证前的安全回滚包。
> 完整哈希与症状定位见 `docs/PACKAGE_LEDGER.md` §2/§3；歌词问题的原因与适用范围见
> `docs/PITFALLS.md` §38；未完成项见 `docs/TODO.md`。

---

# 11. 已达成的状态（供对照，非问题）

以下为**已修复/已完成**，列出以避免误报：

- 字库覆盖率 100%、缺字清零（v2.13/v2.14）。
- 女神选项（Change Clothes / Window Skin / Timer Skin）闪退已修（v2.19）。
- 选章节/选关闪退已修（v2.59/v2.61）。
- 说话人名已上屏（v2.49 槽位级放行）。
- "勇者城"已恢复（v2.65）。
- DLC01 文本错乱已修并纳入装机流程（v2.47）。
- 多行台词"只显示第一行"已修（v2.5 起）。
- 小咕之歌歌词已汉化（v2.31：cscv `blob355` 歌曲表 28 个英文行 + 主线 LANG `blob1025`）。
  **适用范围（2026-10-30）：** 旧配方（`apply_menu`）一直有；Z 系列曾因 `song=False` 丢失，
  2026-10-30 起 Z19 重新包含（Z18/Z20 仍为空，见 `PITFALLS.md` §38）。
- 各章节关底歌词浮层已补全（2026-10-20：14 个 stage blob 的歌词槽一并放行，
  `SONG_OK` 收录 34 条原串；此前只有第四章第 1 行被 `ui_always` 顺带放行，其余呈"半中半原"。
  见 `PITFALLS.md` §21、`TECHNICAL.md` §5.3.2）。
  2026-10-20 统一改为**以日文原文为源**重译 43 个歌词槽（旧译文派生自英文/3DM，存在按英文意译
  与串行错位），其中 `道だから`（`b796`）原缺译文，已补 `text_v2.csv` row 61238。

---

# 12. 未登记 blob 的显示文本（不翻 ≠ 受保护）

**Status:** Partially fixed　**Severity:** Low

**症状：** 部分对话/系统消息在游戏里仍是原文（日文或英文），但这些串**不在** collide 白名单里，
即它们**并未受保护**，只是所在 blob **整体没有登记进 `text_v2.csv`**，构建器逐槽改写时直接跳过。

**已排查（2026-10-20，全库扫描未登记且 JA≠EN 的 blob）：**
- **不受保护、理论上可译**（官方 EN 版均已译、cscv 中无按名比对孪生，或仅系统消息类）：
  `b252` 鱼人族台词、`b675` 無限クリア/マスター、`b774` 壶商人 NPC 对话、`b794` 攻/防提升提示、
  `b883` 炮台破坏提示、`b891` 回复道具提示、`b845` 音乐/章节名表、`b1010` 服装定义段。
- **受保护**（命中 collide，按名比对）：坐骑名（`船/馬/ドラゴン/バイク/バギー/タケウマ`）、
  `勇者城`、`ヘルファイア`、以及 `b630` ダメージをうけた！/`b845` イントロ 等（后两者疑似**假命中**，
  可参照 `SONG_OK` 机制核查后放行）。
- **不可译**：截图里的说话人名 `YuJa` 在 LANG_JA/LANG_EN/cscv/exe 全库 0 命中，是运行时/存档动态值。
- **非文本**：`b44/b140/b155/b238/b383/b634/b648/b664/b698/b805/b968` 为二进制/压缩数据。

**已修：** 已补 22 个登记槽（`text_v2.csv` row 61239–61260），dist 重建并逐槽校验
（长度 = 2×字数、无 `?`、槽外零差异）：
- `b252` off2928 `魚人族「まだ悪い魚人がいる！　助けてくれー」`
  （= 截图里的 `Mermaid Clan: There are still Evil Mermaids! Help me!`）。
- `b675` off1216/2092 `無限クリア`/`無限マスター` → `无限通关`/`无限大师`
  （与已译的称号表 `b931` 同译，避免同名不同译）。
- `b774` off4296/4448/4600 壶商人三句 NPC 对话。
- `b794` off40/344/648 攻/防提升提示（EN 版把「防御力」也印成 `Offense`，属官方译文错误，此处以日文为源）。
- `b883` off12352…15088 共 10 处 `ほうだいをはかいした！` → `摧毁了炮台！`。
- `b891` off5816/5968/6120 回复味噌/咖喱/牛奶提示。

`b252` 是 CSCV 结构（magic `CSCV`、off4=stride152、off8=记录数78），字符串字段 = 记录起 `+24`、
**字段容量 128 字节**（其后至下一条记录头 `08 00 00 00` 全为 NUL）；此槽 **cscv 无孪生**，无按名比对风险。
`b675/b774/b794/b883/b891` 在 cscv 有**逐字节孪生**，构建会按内容匹配自动同步（这些是消息/台词显示表，
非键名表）；`b675` 的槽位含 4 字节 `FF FF FF FF` 前缀，登记 `offset` 须指向**文字起点**（= 前缀后）。
JA/EN 两侧写入字节一致。

**剩余（需改构建器放行清单，暂未处理；跟踪：`docs/TODO.md` T-04）：**
- `b630` off4752 `ダメージをうけた！` —— collide 命中来自 cscv `b23`（**战斗消息显示表**，
  即 `CSCV_TWINS` 里的孪生表），属**假命中**；需仿 `SONG_OK` 加放行清单后再登记。
- `b845` 音乐/结局曲名表 7 条 —— 其中 `イントロ`/`グランドエンディング` 命中 cscv `b814`
  （同为 stride204/7 条的曲名显示表，假命中）；需放行后才能整表统一翻译，否则呈"半中半英"。
- `b1010` 服装定义段（`handR=`/`foot=` 等）—— 是**装备名**且 `b984` 为 cscv 逐字节孪生，
  属名字一致性范畴，应走名字批次（全副本同改）而非单表登记。
- 截图里的说话人名 `YuJa` 在 LANG_JA/LANG_EN/cscv/exe 全库 0 命中，是运行时/存档动态值，不可译。

**2026-11-04（Z22，低风险批）：** `b25` 键值型 UI 消息表的值列已整列补译 298 条
（城堡自定义面板、道具类型/等级、`名称：%s　类型：%s`、`活动道具`、铁匠铺、地图编辑器与在线菜单），
`b99` 合成说明首段 2 条、`b642` 武器种名 12 条、`b763` 按键名整列、`b186` `Switch`。
`b25` 的记录键（`CATSLE_F1`/`TownIS10`…）保持原样，只改值列；Q16 键名
（`Customize Hero Castle`）仍按 §4 保留原文。构建自检 error 0 / warning 45。
注意：纯数字原文（`1`/`2`…）不可翻译，否则会被名字副本同步扩散到 ID 字段
（见 `PITFALLS.md` §41）。
**仍保留原文：** `Customize Hero Castle`（Q16 键，见 §4）；`(54,6656)` 的 `Hero<>`
模板槽（占位标记）与 `b509/908` 脚本键槽。图鉴敌人/Boss 列表名已于 **Z23** 上屏
（怪物页 `b734` 138 条、头目页 `b555` 107 条，见 §3）。

---

# 13. 存档中的自定义名字会随载体码重排变化

**Status:** Fixed in development（2026-11-09，cmap 固化已实施）　**Severity:** Medium（存档兼容，历史问题）
**Affected locales:** zh-CN

**症状（修复前）：** 玩家把主角改名为「尤莎」，安装新补丁后名字偶尔变成「允莎」等相邻字。
**原因：** 汉字载体码按字频分配；译表/额外行变化会让码整体平移。游戏内文本每版重编码，
但存档保存的是旧 CP932 字节，补丁不重写存档 → 旧字节被新码表解释成别的字。
实测 Z13→Z14 有 2,526/2,818 个字的码发生变化；ASCII 名字（Yushia/Yuja）不受影响。
**Workaround（旧版本）：** 安装新补丁后重新输入一次名字。
**当前处理（2026-10-22）：** 主角默认名 `b391` rec2/3/4（Yusha/Yushia/Yuja）与
`b715` 示例名已在 Z14 构建中强制还原原文；`translator-view` 中 `Yusha` 归入
`protected/`（原因 `protagonist-default`），因此本版不会再把这些名字写成载体码中文。
**已实施（2026-11-09，T-01）：**
1. `locales/zh-CN/cmap.json` 持久化「字 → 载体码」，`build_plan()` 优先使用固化码；
2. 新字只从载体码池中**未使用的码**追加，旧字不重排、不因译表变化而改码；
3. 固化字即使当前译表暂时不用也继续占格，避免旧存档名字失去字形；
4. 容量不足直接报错（不挤掉旧码）；连续两次构建 `+0 新字`，LANG_EN/texture/cscv 哈希一致；
   2300 个码唯一且均可在字符表反查。
**相关文件：** `docs/PITFALLS.md` §27、`tools/build_cn.py: build_plan()` / `load_persisted_cmap()`、
`locales/zh-CN/cmap.json`。

---

# 14. 宝箱提示“获得××！”但背包没有（Z15 已修，待复测）

**Status:** Fixed in development　**Severity:** High（道具无法获得）
**Affected versions:** Z10b–Z14 及此前包　**Affected locales:** zh-CN

**症状：** 宝箱开启后显示“获得便携女神像！”等提示，但道具未进入背包；
其他宝箱同样只提示不发放。
**原因：** 道具表的名称已中文化，但事件/宝箱脚本参数列（`b219 pos28`、
`b290 pos28`、`b408 pos28` 等）仍是英文；游戏按名字匹配发放，找不到中文道具。
与 Z15 同字复用无关——Z14 中这些槽位同样如此，是更早的道具名翻译未同步全副本。
**修复（Z15）：** `fill_item_name_copies()` 以道具表终串为准，同步全库同名副本；
实测同步 253 处，真实道具名英文副本 0，操作数 260 点 0 失败。
**Workaround：** 使用 Z15 或更新包；Z14 及更早仍有此问题。
**相关文件：** `docs/PITFALLS.md` §28、`docs/PACKAGE_LEDGER.md` §3/§7。

---

# 15. 载具/坐骑（龙、船、马等）在关卡里不出现

**Status:** Fixed in development　**Severity:** High（剧情 NPC/载具缺失）
**Affected versions:** Z10b–Z15（修复前）　**Affected locales:** zh-CN

**症状：** 过场演出中本应出现的「奇尔多尼克斯」（Childonyx，龙）在中文下完全不见；
同一 build 切日语正常。船、马、摩托、越野车、竹马同样受影响。
**原因：** 道具表载具名已中文化，但关卡实体表（`stride 152 pos24`）的同名副本未同步；
该字段紧跟 float `-1.0f` 尾字节 `80 BF`，无 NUL 分隔，旧同步/审计匹配不到。
**修复（Z15）：** `fill_item_name_copies()` 增加嵌入副本分支，本篇同步 35 处。
**验证进度：** 龙已实机确认恢复；**DLC Q78 船见 §15.1，待复测；马/摩托/越野车/竹马未逐项实机测试。**
**相关文件：** `docs/PITFALLS.md` §29、`build/_scratch/audit_mechanic_replicas.py`。

---

# 15.1 DLC01 载具/实体名未同步（Q78 船）

**Status:** Fixed in development　**Severity:** High（DLC 关卡载具不出现）
**Affected versions:** Z10b–Z15（修复前）　**Affected locales:** zh-CN

**症状：** DLC01 Q78 触发造船事件后「船」不出现；JA 正常。
**原因：** `fill_item_name_copies()` 只处理主 `res/LANG_EN.s2a`；DLC 的
`b45 stride152 pos24`（19 条）、`b76 rec9`、`b97 rec5` 仍是 `Boat`。
**修复（Z15）：** 新增 `fill_dlc_item_name_copies()`，由 `refresh_dlc01()` 自动调用；
DLC 同步 102 整槽 + 23 嵌入；DLC 审计未同步 = 0。
**Workaround：** 使用修复后的 Z15。今后审计必须同时覆盖本篇与 DLC01。
**相关文件：** `docs/PITFALLS.md` §29.1、`tools/build_cn.py`。

---

# 16. DLC01 台词整段乱码

**Status:** Fixed in development　**Severity:** High（DLC 可读性）
**Affected versions:** Z11–Z15（修复前）　**Affected locales:** zh-CN

**症状：** DLC01 台词出现形近错字（「啊哈哈，抱歉抱歉」→「啊哈哈，剩建剩建」）；本篇正常。
**原因：** 主装机使用带 `_EXTRA_ROWS` 的 cmap，而 `refresh_dlc01()` 在其被清空后重算 cmap；
字符表与 DLC 文本使用两套载体码。
**修复（Z15）：** `build_plan()` 缓存 `_LAST_BUILD_PLAN`，`refresh_dlc01()` 复用主 cmap。
**验证：** 解码恢复「啊哈哈，抱歉抱歉」；DLC 结构改动 0。
**相关文件：** `docs/PITFALLS.md` §30。

---

# 17. DLC 防具从装备栏消失

**Status:** Fixed（2026-10-23 实机确认泳装已回到装备栏并正确命名）　**Severity:** High（装备不可用）
**Affected versions:** Z10b–Z15（修复前）　**Affected locales:** zh-CN

**症状：** DLC 防具「セクシーみずぎ / Sexy Swimsuit」从装备栏消失；道具表大量
`pos0` ID 与 `pos140` 进化链 ID 被清零。
**原因：** `_is_name_like()` 把数字 ID 当名字，`sync_name_replicas()` 传播空译文。
**修复（Z15）：** 严格 CP932 校验 + 空译文不传播。
**验证：** 道具表记录前 4 字节改动 0；泳装 ID 完好；名称恢复「性感泳衣」
（Z18 起补全了此前被缩写成「性感泳」的说明页首行，见 `PITFALLS.md` §36）。
**相关文件：** `docs/PITFALLS.md` §31。

---

# 18. 职业成长数值 / 称号条件 ID 被清零

**Status:** Fixed in development　**Severity:** High（职业属性/称号）
**Affected versions:** Z14–Z15（修复前）　**Affected locales:** zh-CN

**症状（静态发现）：** `b128` 职业表 pos36/44/48/52/56 成长数值被清零；
`b931` 称号表 pos32 条件/ID 字段被清零。
**原因：** `_z14_rows()` 的 `force_sb` 过大（`b128=64`、`b931=36`），写前整段清零覆盖相邻字段。
**修复（Z15）：** 改为 `(128,212,4,32)`、`(931,292,0,32)`。
**验证：** 结构审计：主 LANG 仅 2 处预期操作数重算，职业/称号数值改动 0，DLC01 0。
**相关文件：** `docs/PITFALLS.md` §32、`build/_scratch/audit_structural_changes.py`。

---

# 19. 替换词典的编辑方式与导入自检

**Status:** Implemented　**Severity:** —（使用说明）

- 可直接编辑 `translator-view/dict/替换词典.json`，然后运行「汉化-导入校对.bat」；
  导入会校验条目、备份并写回 `replace_map.py` / `hl_map.py`，然后重建。
- 只改词典、不改任何校对 JSON 也会重建。
- REPL 条目不能含 `% $ { } < > #`；HL 的尖括号必须成对；键值不能为空/含控制字符。
- 导入后会运行构建自检（名字副本、操作数、重名/碰撞、token、DLC）。
  致命错误会**自动回滚**本次导入并恢复 dist，退出码 1。
- 基线：Z15 为 error 0 / warning 45（纯显示类重名，不阻断）。
- 词典改动会改变字频 → cmap 重排，旧存档自定义名可能漂移；DLC 会自动重编码。
**相关文件：** `docs/PITFALLS.md` §33、`tools/validate_build.py`、`tools/import_review.py`。

---

# 20. 视频硬字幕：RAGNAROK 对话仍略早于音频

**Status:** Open（暂不解决）　**Severity:** Low（演出同步）
**Affected versions:** Z16-video　**Affected locales:** zh-CN

**症状：** RAGNAROK 制作名单视频（`LANG_EN.s2a` `1297f874`）中段的女神对话，
出现时间仍比音频略早；中段卡顿与瞬间杂音已修复。
**技术说明：** 原视频为 VFR 且结尾有约 5s 长静帧；单遍重编码保留原时间轴、
末尾用 `tpad=0.7` 克隆最后一帧补足 BGM，仍会丢失约 0.3–0.4s 的尾部，
从而产生整体前移感。逐句调 `start/end` 只能缓解个别句，无法保证全段随音频。
**Workaround：** 暂无。后续可考虑运行时字幕叠加（完全不动视频/音频）；跟踪：`docs/TODO.md` T-08。
**相关文件：** `docs/PITFALLS.md` §25.26、`locales/zh-CN/video/videos.json`。

---

# 21. 显示文本漏译：Z17 第一轮排查结果

**Status:** Partially fixed　**Severity:** Low（可见性）
**Affected versions:** Z17-display-fill　**Affected locales:** zh-CN

**已补全（纯显示，不涉机制名）：**
- 括号独白/选项（`（…）`）不再被 collide 挡住；
- `Change Clothes` 菜单 The Usual/Robe/Swimsuit/Dress/Music Player；
- 图鉴 Boss/Artwork 页签；合成 Class Change/Craft Weapons/Specialty；
- 战斗菜单 Bring Allies Back to Life；
- 日文单行、英文多行造成的 8 个孤立尾行（`moving.` 等）已补行清零；
- `b763`/`b354`/`b516`/`b186` 一批纯 UI 标签；
- `b804` 萨莎日记/魔王勋章/魔人迷宫标题、`b291` 地图编辑器说明/半句、
  `b153` 战斗行动提示（我走啦/我停下来）已放行；
- `S-I-L-E-N-C-E!`、`I have no regrets!`、`Entered tent!`、样例地图说明已补译。

**机制名（2026-11-06 复核）：**
- 道具名 `Mu`（ミュー）/`Xi`（クシー）已于 Z18 补译（缪/克西），图鉴敌名/Boss 名已于 Z23 上屏
  （Z24 再做跨表专名统一）。
- 区域名等仍按守卫保留原文；它们参与按名哈希/发放，不能按说明文单独补译。

**待后续：** 道具/技能说明中的短句（`b147/357/736/666`）、
`1,000m/h Wind`/`10,000m/h Wind`（技能名，需整批机制名处理）；跟踪见 `docs/TODO.md` T-05。
（`b34` 关卡/章节标题已于 2026-11-06 复核：222 条记录中 118 条名称已改为中文，
Q16 rec49/142 按守卫保留，不再列入待办。）
**相关文件：** `docs/FINAL_QA_PLAN.md` §2.2、`tools/build_cn.py`（`display_release_hit` / `DISPLAY_RELEASE_OFFS`）、`locales/zh-CN/menu_ok.json`。

---

# 22. 道具描述错字：`0x5F`（`_`）被当断行控制符（含便携女神像/升级药水）

**Status:** Fixed（2026-11-04 Z21 实机验证通过，已并入 Z19 / stable 基线）　**Severity:** Low（仅物品信息描述）
**Affected versions:** Z17 起（含 Z18/Z19/Z20）　**Affected locales:** zh-CN

**症状：** 便携女神像（`Goddess Porta-Statue`）描述显示 `便携女挑♥`；
樵夫斧描述显示 `毛v用的斧。`（应为 `樵夫用的斧。`）；升级/降级药水说明也曾异常。
同一界面的**物品名**始终正常。

**真因（2026-11-04 更正）：** 原版英文道具说明用 `_`（字节 `0x5F`）作**断行标记**；
描述路径按原始字节在 `0x5F` 处切分，因此当某个字的 CP932 码**尾字节**为 `0x5F` 时，
该字会被从中间劈开，后续字节错位：
- `樵` 的载体码 `8B 5F` → `8B|95`＝毛 + `76`＝ASCII `v` ⇒ `毛v用的斧。`
- `神` 的原生码 `90 5F` → `90|91`＝挑，末尾孤立字节变 ♥ ⇒ `便携女挑♥`

旧结论“载体码 `0x9091` 与 `0x905F` 查表冲突”**作废**；这不是字符表/排序表问题，
也不是缺字或容量问题。详见 `docs/PITFALLS.md` §40。

**修复：** Z21（`package_names_cn_reuse_z21`）：
- 载体码池禁用 `0x??5F`；原生码尾字节为 `0x5F` 的复用字（神/点）改分配安全载体码；
- 撤销 `PROTECTED_DISPLAY_OFFS`，便携女神像说明恢复中文；
- 译表恢复 10-30 避字前的「用后升1级的神奇饮料 / 用后降1级的凶险饮料」；
- `validate_build.py` 新增描述尾字节检查（本篇 + DLC01），命中即 error。

**残留风险：** 若译文用字出现新的“排版控制字节”尾字节（目前只确认 `0x5F`），
校验会拦截；原生日文描述本身也有同类潜在缺陷（原版很少触发）。

**相关文件：** `tools/build_cn.py`（`UNSAFE_TRAIL_BYTES` / `carrier_pool` / `build_plan` /
`PROTECTED_DISPLAY_OFFS`）、`tools/validate_build.py`（`_check_desc_trail`）、
`locales/zh-CN/text_v2.csv`（row 60803/60935/61089、61041/61042）、
`docs/PACKAGE_LEDGER.md`（Z21）。

---

# 23. 购买音乐播放器列表闪退：菜单项名与 b280 分组标签再次不一致

**Status:** Fixed（Z17）　**Severity:** High（进入即闪退）
**Affected versions:** Z17 前一版　**Affected locales:** zh-CN

**症状：** 在女神商店选择「音乐播放器」并确认进入购买列表时游戏闪退；
日文版同一操作正常，列表标题为 `ミュージックプレイヤー ON`。

**实际原因：** 与 `PITFALLS.md` §9（v2.19 女神选项闪退）同一类问题：
- 菜单项名 `Music Player` 已翻译为「音乐播放器」：
  `b534/240`、`b534/280`、`b280/1476`、`b186/137664`、`b763/5648`；
- 但 `b280/1444` 的**分组标签**仍是英文 `Music Player`；
- 游戏按「分组标签文本 == 菜单项名」匹配，匹配失败后进入空指针/闪退。

**同类隐患（本轮一并修复）：**
- `Craft Weapons`：`b410/956` 分组标签未译，其余 5 份已译；
- `Gallery`：`b186` 两份已译「图集」，`b280/3484/3688/3892/4096` 四份分组标签未译；
- `Normal Mode`：`b354` 已译「普通模式」，`b186/94656` 未译；
- `Best Time`：`b358` 已译「最快时间」，`b763/9872` 未译。

**修复：** 把上述遗漏副本统一成同一中文串（音乐播放器 / 武器合成 / 图集 /
普通模式 / 最快时间），并在 `DISPLAY_RELEASE_OFFS` 中显式放行对应槽位。
复查后只剩两类**有意保留**的差异：
- `Hero Castle`：`b265/b353/b370/b688` 是 Q16 键，必须保留原文；
- `Title`：`b186` 7 份的日文原文也是 `Title`（JA==EN 内部键），不翻译。

**审计规则：** 任何菜单项名/UI 标签一旦翻译，必须检查**所有同名副本**，
尤其是 `b280` 分组标签；要么全部统一为同一中文串，要么全部保留原文。
复查脚本：`build/_scratch/audit_menu_name_copies.py`、
`build/_scratch/audit_partial_menu_translations.py`。

**相关文件：** `tools/build_cn.py`（`DISPLAY_RELEASE_OFFS`）、`locales/zh-CN/text_v2.csv`。
