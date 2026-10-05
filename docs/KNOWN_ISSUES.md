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

# 1. 名字类中文化结论尚未收敛

**Status:** Investigating　**Severity:** Low（可见性）
**Affected locales:** zh-CN

**症状：** 部分名字类（称号/伙伴/职业/阵形/装备/技能/敌人等）在部分位置仍显示日文（英文模式显示英文）。
**技术说明：**
- 历史两次实锤（露露菲实验、测试 E）后曾得出"名字保留原文定局"；
- 2026-09-18 起改用"仅写 LANG + 同一语言文件内全副本同改 + cscv 全保日文 + 账本回滚"的方法，
  实验 D/E 出现反证（武器技恢复触发），并已分批实施（账本 24 批 / 44,129 槽）；
- 但同日的两份评估文件结论相互冲突，**最终以实机验证为准**。
**Workaround：** 通过 `汉化-名字类回滚.bat` 可一键退回任意批次。
**相关文件：** `TECHNICAL.md` §8、`_work/name_ledger.json`、
`_work/outputs/名字类全量中文化可行性评估-20260918.md`、`键值同改历史复核与本轮结论修正-20260918.md`。

---

# 2. 剧本对话误译（TODO-5，最大未完成项）

**Status:** Open　**Severity:** Medium（翻译质量）
**Affected versions:** 当前装机全部版本　**Affected locales:** zh-CN

**症状：** 部分对话译文与日文原文含义不符（如 `Thank you so much`、`Discussion over.`、
`My control is waning` 一类被英文本二次创作改写）。
**触发：** 剧情/支线对话。
**实际原因：** 主译表以 **3DM 补丁**为底本，3DM 又以**英文本**为底本；英文版本身存在失真。
**影响范围（已评估）：** 对话表族真句子台词槽约 **21,376 槽**（F292 16,012 / F424 3,329 / F196 2,035），
覆盖 **724 个 blob**。
**Workaround：** 暂无（逐句修订中）。
**Technical notes：** 计划全部改回日文本意、保留改前副本、逐批回滚。当前进度 **1/724 blob**。
**相关文件：** `_work/outputs/TODO-待办清单.md`、`_work/outputs/TODO5-*.md`。

---

# 3. 敌人名与敌人专用招式名

**Status:** Open（规划未实施）　**Severity:** Low
**Affected locales:** zh-CN

**症状：** 敌人名（图鉴/战斗/招募提示）与敌人专用招式名在游戏中仍为原文。
**技术说明：**
- 敌人名约 700 名 / 约 7,660 副本（官方 EN 100% 改过 => 可翻）；图鉴名集 104 + 敌数据名集 ~600。
- 敌人专用招式仅约 5 个；其余走玩家技能表。
- 教训：技能/名字跨表按名关联，须"EXACT 全副本同改"，并**先做键名列排查**再动手。
**相关文件：** `_work/outputs/敌人名与敌人技能名-可翻译性评估.md`。

---

# 4. Q16 相关台词仍为原文

**Status:** Won't fix（已知可见代价）　**Severity:** Low
**Affected locales:** zh-CN / en（按语言显示各自原文）

**症状：** 含"勇者城"的约十几行台词（`196/28`，日文侧 14 + 英文侧 14 处）保持原文。
**技术说明：** 这些串同时是"按键名查找"的标识，必须保留（`restore_q16_keys()`）。
   这是修复"勇者城消失"的必要代价，不是故障。
**相关文件：** `_work/outputs/Q16勇者城-第二版根因与修复-20260918.md`。

---

# 5. 制作人员 / 版权页姓名的字形差异（历史代价）

**Status:** Fixed in development（v2.14 起恢复原版字形）
**Severity:** Low

**说明：** v2.7 曾回收 index 1024–1119 的版权/制作人员姓名汉字区以扩格，
代价是版权页日文姓名显示为汉字乱码。**v2.14 起不再回收原版 index 0-1247**，该代价已消除。
**注意：** 若回退到旧策略（`RECLAIM_STAFF=True`）会重新出现此问题。

---

# 6. 少量 UI 标签仍为原文

**Status:** Workaround available（可选增强未默认安装）　**Severity:** Low
**Affected locales:** zh-CN

**症状：** 个别纯 UI 标签/提示（如 `はなす`/交谈、`女神像ワープ`/女神像传送等 14 串）仍为原文。
**技术说明：** "UI 词表版"（额外放行这些串）已实现但**未默认安装**，待实机实测确认。
**Workaround：** 使用 UI 词表版安装（见历史 bat）。
**相关文件：** `_work/ui_always.json`、`_work/outputs/未翻译文本排查报告.md`。

---

# 7. 极端生僻字可能显示 `?`

**Status:** Partially fixed　**Severity:** Cosmetic
**Affected locales:** zh-CN

**症状：** 极少数生僻字显示 `?`。
**技术说明：** 图集格容量有限（扩容后 2847 格，已用 2788，余量 59）；未覆盖字回退 `?`。
**已知个例：** 制作人员名 `row1992`（"小城崇志"）终态含字库外字"崇"且超容量 -> 跳过。
**相关文件：** `verify_charset_full.py`、`_work/outputs/减少问号-方案评估.md`。

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
**技术说明：** 见 `PITFALLS.md` §5/§6/§7/§11。
**缓解：** 每次装机后跑 `t34_health.py` 体检 + `t162` 差异审计；实机抽检技能/称号/同伴攻击。

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
- 小咕之歌歌词已汉化（v2.31）。
