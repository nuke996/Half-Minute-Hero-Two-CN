# 正式版前全量漏译排查（FINAL_QA_PLAN.md）

> 状态：**进行中**（2026-10-21 记录；2026-10-22/23/24/25/27/30、11-06、11-09、11-21/22 更新，供新对话直接接续）
> 2026-11-09：第二轮对话校对完成（待核对 429 → 0，427 修复 + 2 保留原译，见
> `docs/PROOFREAD_DIALOGUE_ROUND2.md`）；cmap 固化已实施（`locales/zh-CN/cmap.json`）；
> **发布基线 Z19 已启用 Z23 敌名/Boss 图鉴列表名**，stable/E3 保留原文作为安全回滚包。
> 校对入口与导入目标仍是 `locales/zh-CN/translator-view/` → `CURRENT_REVIEW_RECIPE=z27`
> （`dist/Z27-subcommander/`）。Z22–Z27 均未实机；除实机测试外的未完成项见 `docs/TODO.md`。

---

## 1. 目标

在不动机制键、不引入新 bug 的前提下，找出并补齐**玩家可见但仍为原文**的文本，
包括：

- `text_v2.csv` 已登记但未放行 / 未翻译的显示槽；
- 未登记进 `text_v2.csv` 的显示表（如 `b99` 合成、`b25` Materials）；
- 代码内额外译表行（伙伴名/技能名/合成 UI，见 `50_extra.json`）；
- 少量 UI 标签、图鉴/收藏名、地图编辑器说明等。

**不包含**（刻意保护，勿动）：

- `b931 pos36` 章节标题副本、Q16 记录、`b317` 连携技表；
- 脚本 token（`SE2_SKILL`、`$X`、`%s`、`100%_Fire`、`#RG`、`Disable/Enable` 等）；
- 二进制/压缩数据与运行时动态值（如 `YuJa`）。

---

## 2. 已知待办清单（2026-10-21 实机截图）

| 位置 | 现象 | 性质 | 处理建议 |
|---|---|---|---|
| 道具收藏列表 | `Mu`、`Xi` 等少数名称仍英文 | **已补（2026-10-27，Z18 起）** | 已译 缪/克西，见 §2.3；仍需实机确认可获得/装备 |
| 怪物图鉴第 1 项 | `Jelly` | **已补（Z23）** | 图鉴列表名已为「果冻怪」；`b734+72` 小槽容量只够「果冻」，属有意缩写 |
| 地图编辑器 `Explanation` 栏 | 中英混排说明 | **已补（Z24）** | `b291` 206 槽按日文整句重译；全库 `Explanation` 英文残留 0 |
| 合成界面 `Class Change` | 仍英文 | **已放行（Z17）** | 现为「职业变更」，见 §2.2 |
| 合成界面 `Specialty` | 仍英文 | **已补（Z17）** | 现为「擅长」，见 §2.2 |
| 其它零散 UI | 待全量扫描 | — | 按第 3 节流程处理 |

> 2026-10-21 已修：`Wooden Sword +1`→木剑+1、合成说明首行、`Materials:`。
> Z14 已补：Chaos Wing 等新敌技名。

---

## 2.1 开放测试项（2026-10-22/23，Z15 补丁轮）

1. **载具/坐骑**：龙（Childonyx）已实机确认恢复；**DLC01 Q78 的船**已在离机侧修复
   （`DLC01/LANG_EN.s2a` 实体表 Boat→船，21 处），待实机复测；**马/Horse、摩托/Bike、
   越野车/Buggy、竹马/Bamboo Stilts** 尚未逐关验证。本篇与 DLC01 都要测。
2. **DLC01**：台词乱码（PITFALLS §30）、泳装回到装备栏并可装备且名字为「性感泳衣」
   （PITFALLS §31）——均待复测。
3. **职业/称号数值修复**（PITFALLS §32）：职业成长数值、称号条件是否正常；
   Z14 起 `b128` 成长字段与 `b931 pos32` 条件 ID 曾被清零，已修但未实机复测。
4. 结构审计基线：`python build/_scratch/audit_structural_changes.py`
   期望“主 LANG 仅 2 处操作数重算、DLC01 0 处”；
   `python build/_scratch/audit_mechanic_replicas.py` 期望“14 类英文副本 0、
   嵌入副本 0、DLC 未同步 0”。

## 2.2 Z17 第一轮漏译排查（2026-10-24）

**已补全（纯显示，不涉机制名）：**

- 括号独白/选项：`（…）` 开头的对话行不再被 collide 挡住（如亚修自言自语、莱万
  “比公主更不懂世故”、`I'm sure I can handle it!` 选项）；
- `Change Clothes` 菜单：`The Usual`→老样子、`Robe`→长袍、`Swimsuit`→泳装、
  `Dress`→连衣裙、`Music Player`→音乐播放器；
- 图鉴页签：`Boss`→头目、`Artwork`→插画；
- 合成/战斗菜单：`Class Change`→职业变更、`Craft Weapons`→武器合成、
  `Bring Allies Back to Life`→复活同伴、`Specialty`→擅长；
- 日文单行、英文多行造成的孤立尾行（`moving.`/`ready.`/`village.`/`humans.`/
  `kidnapped.`/`either.`/`anyone.`）已补行并用全角空格清零；
- 网络/地图 UI 标签（`b763`/`b354`/`b516`/`b186`）一批纯 UI 串放行；
- `b804` 萨莎日记 4 种×5 份、魔王勋章 84/85、30 个魔人迷宫标题、检查选项已放行；
- `b291` 地图编辑器说明/半句按记录重译（说明、外观/强度/数量、洞穴/捷径位置等）；
- `b153` 战斗行动提示（我走啦/我停下来）、`S-I-L-E-N-C-E!`、`I have no regrets!`、
  `Entered tent!`、样例地图说明已补译。

**机制名（Mu/Xi 已补全，其余保留）：**

- **（2026-10-27 已改判）** 道具名 `Mu`（ミュー）、`Xi`（クシー）已在 Z18 补译为
  缪/克西，3 份副本全部同步、名字哈希操作数已重算、`validate_build` error 0；
  仍待实机确认这两件武器能正常获得/装备（见 §2.3）。
- 其余 `b137`（区域名）、`b656`（帝国兵）、`b290`（无限亚修/无限魔王）等
  名字类同理保留原文。
- `1,000m/h Wind` / `10,000m/h Wind`：技能名，命中 `b83/b394` 操作数，
  需走完整机制名批次，不能按说明文补。

**待后续处理（以下为 Z17 当时状态；T-05b/Z25、Z26 已完成，剩余见 T-04/T-10b）：**

- 道具/技能说明中的能力名与发动率短句（`b147/357/736/666`）仍英文，暂未补行；
- `Catch and Release`（`b172` 2 处）、`Beam Security`（`b444`）、`Thunder Storm Breath`（`b750`）
  等敌/技能名保持原文；
- `1,000m/h Wind`/`10,000m/h Wind`（`b147/357/666/736`）需走整批机制名处理。
- ~~`b34` 关卡/章节标题~~（2026-11-06 复核：222 条记录中 118 条名称已为中文，Q16 rec49/142 保留）。
- 跟踪：`docs/TODO.md` T-04（纯显示与假命中）/ T-10b（技能/机制名遗留）。

## 2.3 Z18 截图校对轮（2026-10-27，待实机复核）

1. **跨槽台词重复**：`row 14180`（`b260`）第二行原译重复了上一行的 `<地震>/<落石>`，
   现为 `　用这些招数来攻击你吧。」`。
2. **`AVALANCHE!` 补译**：该槽此前从未进译表，一直显示英文；现为
   `　雪崩要来了！」`（`b510/21264`，`row 61303`）。
3. **选项语义**：`row 27053/27054` 现为 `「在下列选项中，` + `　哪样魔王兵器还没有登场？」`，
   已恢复“尚未登场”。
4. **装备名全名**：Alpha/Beta/Delta/Epsilon/Iota/Omicron/Sigma/Phi/Omega/Balmung 补全为
   阿尔法/贝塔/德尔塔/埃普西隆/伊奥塔/奥米克戎/西格玛/法伊/欧米伽/巴鲁蒙格；
   `Mu`/`Xi` 首次补译（缪/克西）；`Sexy Swimsuit`→性感泳衣、`Wood Stick`→木杖、
   `Hero Cloth`→英雄十字（说明页首行与名字列统一）。
   **实机重点**：图鉴/装备栏名字是否完整，且 **Mu/Xi 仍能正常获得/装备**
   （名字参与哈希操作数，见 PITFALLS §36、§34 改判）。

---

## 2.4 Z19 校对轮 + 歌词恢复（2026-10-30）

1. **对话校对已入库**：`proofread` 分支共 1821 单元 / 2842 处条目（2716 单行槽 +
   86 多行整段 + 40 DLC），详见 `docs/PROOFREAD_DIALOGUE_REPORT.md`；**2026-11-09 第二轮
   把最后 429 条待核对全部清零（427 修复 + 2 保留原译，529 槽）**，逐条对照见
   `docs/PROOFREAD_DIALOGUE_ROUND2.md`。
2. **「小咕的歌」歌曲表恢复中文**：Z14→Z20 共用配方改 `song=True`，`cscv[355]` 的
   28 个英文行写回中文；`place`/`chap` 仍关闭（`PITFALLS.md` §38）。
   实机重点：音乐播放器「小咕的歌」页应是 日文行 + 中文行，间奏 `♪` 行不变。
3. **Z20 实验包**（`dist/Z20-desc-dodge/`，2026-10-30 19:15）：Z19 + 道具说明避字，
   用于验证"描述渲染器按码错位"假设；**它构建于歌词修复前，不含歌词**，不作为发布基线。
4. **歌词校对入口（2026-11-22 T-03 已完成）**：歌词译文导出为
   `translator-view/60_songs.json`，改后导入写 `song_en_lines.json` 并重建；
   无独立译表行的装备名副本见 `protected/prot_itemcopies.json`（只登记）。

---

## 2.5 Z30 / Z32 单机回归清单（2026-11-24）

> 只列单机可见项；Ad Hoc 1–8 预设的 21 处鞋名属**联机内容**，不在此清单。
> **Z31 已作废**（序章装备丢失），不要测试；当前校对目标为 **Z32**。

| 版本 | 位置 | 变更 | 验证方式 |
|---|---|---|---|
| Z30 | Q19「风之塔」 | `#PARTY(Knight)` → 骑士 | 进关确认骑士伙伴出现在主角下方 |
| Z30 | Q63「石化世界」 | `#PARTY(Rurufi)` → 露露菲 | 进关确认露露菲出现 |
| Z30 | Q73「了结之时」 | `#PARTY(True Geezer)` → 真大叔 | 进关确认伙伴出现 |
| Z30 | Q73 | `#HERO_CATSLEPARTS1..5` → 水晶城堡 | 走到城堡战/放置零件，确认不闪退 |
| Z30 | Q16「勇者城」 | `b358 rec818 pos112` UI 键写回 `Hero Castle` | 打开 Q16 城堡相关菜单，无缺字/空白项（可能不直接显示文字） |
| Z32 | 称号一览 | 5 个称号改名：不许色色 / 掀裙全制霸 / 不许筑城 / 反杀 / 夺取天下！ | DLC 内获得或查看称号列表 |
| Z32 | DLC 剧情「好色鸟」 | 说话人名 缺爱公鸟 → 饥饿公鸟 | 该段对话说话人显示「饥饿公鸟」（台词 `Caaaw, cacaaaw!`） |

**范围确认：** Z30 相对 Z29 只改 4 个 blob、9 处（上表前 5 行）；Z32 相对 Z30 只改
主 `b34`（Ad Hoc，联机）、`b931`（5 个称号名）、DLC `b7`（1 处敌名）。texture / cscv /
MOV 在两者之间逐字节相同。

**相关：** `docs/KNOWN_ISSUES.md` §26–§29、`docs/PITFALLS.md` §54、`docs/TODO.md`
T-17/T-19/T-20/T-21。

---

## 2.6 联机静态结论与实机清单（2026-11-25）

> 静态分析详见 `TECHNICAL.md` §10.3.14。结论：协议不传名字/哈希/版本，
> 主要风险是“本地文本/编码跨版本不一致”。**以下全部未实机**。

| 组 | 步骤 | 预期 | 失败时记录 |
|---|---|---|---|
| A 同版本双补丁 | 两名玩家用**同一发布包**建房/进房 → 开局 → 放技能 → 结算 | 正常；Ad Hoc 1–8 预设装备齐全（Z32+）；远端名显示 Steam 昵称 | 失败阶段、双方 `build_manifest.json` 配方与哈希 |
| B 混联 | CN 补丁 + 原版（同 BuildID `381930`）建房/进房 → 开局 → 放技能 → 结算 | 预期能进房；技能/实体正常 | 无法进房 / 不同步 / 实体缺失 / 闪退的具体阶段 |
| C 自定义地图 | 一方在**同版本**下建图并让对端加入；再用另一版本建图重复 | 同版本正常；跨版本文本可能乱码/缺字 | 地图作者版本、乱码字段 |
| D 英雄名 | 双方改名（含中文/载体码字）后进房 | 同版本正常；跨版本或与原版可能乱码 | 双方 cmap/版本 |
| E 日语路径 | 把 Steam 游戏语言设为日语后再联机 | 当前只写 EN 的发布包：该端显示日文（未汉化）；联机本身正常 | 是否影响进房/同步 |
| F 排行榜/战历 | 完成一局后查看战历/排行 | 分数正常，无名乱码/统计丢失 | 条目截图 |
| G 存档/ID 对照（离线，可与 A/B 并行） | 游戏内只换一件唯一装备（如 Red Bandana）→ 保存 → 对比 `hmh2save_*.h2s` 的 `+0x3C..+0x4C`；再 diff 两个进度不同的存档 | 5 槽顺序与 pos0 ID 可确认；背包/技能区可逐步定位 | 存档路径、槽位值、道具表命中 |

**注意：** 任一方执行 Steam「验证文件完整性」会还原补丁文件，等同退化为混联（组 B）。
G 的解档方法见 `TECHNICAL.md` §10.3.14 §2.3/§2.4、`docs/FILE_FORMATS.md` §9、`docs/TODO.md` T-22。

---

## 3. 排查流程（建议按顺序）

1. **以当前校对目标 `dist/Z27-subcommander/`（与发布基线 Z19 内容 + T-05b/Z25–Z27）为基线**：
   Z20 是"道具说明避字"实验包，只用于验证描述渲染器，不作漏译基线。
2. **全库扫描**：逐槽比较 `work/original/res/LANG_EN.s2a` 与基线，列出
   “仍为原文、且不是二进制/压缩数据”的槽位。
   - 可复用/扩展 `build/_scratch/audit_untranslated.py`；
   - 参考 `build/_scratch/batchB_plan.py`、`z14_names_plan.py` 的 token 过滤规则。
3. **分类**：
   - A：`text_v2.csv` 有行且有译文，但被 collide/守卫挡住 → 评估是否已实测放行；
   - B：`text_v2.csv` 有行但译文为空 → 补译；
   - C：无 CSV 行（未登记）→ 补行，写入 CSV 或 `extra_review.json`；
   - D：token/键/二进制 → 跳过并记录原因。
4. **逐表确认机制**：
   - 名字类：查 5 个操作数 blob、`cscv` 同串、是否有 stride292/pos32 之类的条件副本；
   - UI/说明类：确认不作为键（查 collide / 脚本引用）；
   - 标题/职业/阵型：沿用 Z14 规则（`skip_blobs` 只剩 317、称号 pos32 同步、Q16 原字节）。
5. **补译**：
   - CSV 行：直接改 `zh_new`（通过 translator-view 导入）；
   - 代码内额外行：改 `50_extra.json`，导入写 `extra_review.json`；
   - 新行：优先生成 CSV 行（带正确 `slot_bytes`）；若会影响 stable，放 `extra_review.json`。
6. **构建与校验**（必须全部通过）：
   - 操作数逐点复算失败 0；
   - `b931 pos36` / `b317` / Q16 原字节改动 0；
   - 无新增 `?`（`GAME OVER<??>` 等字面量除外）；
   - 名字全副本终串一致；
   - 相对 Z14“只增不减”（不得回退已译槽）。
7. **打包**：`package_names_cn_reuse_z19`（不要再用旧的 `package_names_cn_jobs_titles_hash`），
   导出 translator-view 后交付实机抽检。

---

## 4. 工具与命令

```bash
# 构建当前发布包（同时刷新 dist 与校对视图）
python tools/build.py --game-dir work/original package_names_cn_reuse_z19

# 导出校对视图（含 50_extra.json）
python tools/export_review.py

# 导入校对（自检→写 CSV/extra_review.json→按 CURRENT_REVIEW_RECIPE 重建，当前 Z27）
python tools/import_review.py

# 只读盘点（示例）
python build/_scratch/audit_untranslated_z15.py
python build/_scratch/list_blocked_display.py
```

注意：`import_review.py` 现在按 `CURRENT_REVIEW_RECIPE`（当前 **z27** → `dist/Z27-subcommander/`）
重建；不要再用旧的 `package_names_cn_jobs_titles_hash` 刷新本分支的 dist。
发布基线 Z19 用 `python tools/build.py package_names_cn_reuse_z19` 单独重建。

---

## 5. 验收标准

- 玩家可见区域（菜单、图鉴、收藏、合成、地图编辑器、Boss 对话、音乐表）无“明显漏译”；
- 机制抽检全部通过：序章演出、技能/装备/商店、职业/阵型/称号、Q16 勇者城、连携技；
- 所有新上屏文本都能在 translator-view 中看到并修改；
- 导入/回滚可用，`extra_review.json` 与 CSV 都有备份；
- 文档中的映射表（`PACKAGE_LEDGER.md` §7）与实际一致。

---

## 6. 新对话接续提示

新对话开始时建议先读：

1. `docs/PACKAGE_LEDGER.md`（包谱系、映射表、回滚）；
2. `docs/PITFALLS.md` §25（名字/称号/Q16 陷阱）；
3. 本文件；
4. `locales/zh-CN/translator-view/如何校对.txt`。

然后从第 2 节清单开始，不要先改动 `b317`、`b931 pos36`、Q16 与脚本 token。

---

## 7. 载体码（cmap）固化（已完成 2026-11-09，T-01）

> 2026-10-22 记录；**2026-11-09 已实施并验证**。

- 背景：`build_plan()` 原按字频分配载体码，译表变化会让码整体平移；
  存档中的自定义名字是旧 CP932 字节，换补丁后会串字（尤莎→允莎）。
- 现状：主角默认名 `b391 rec2-4` 与 `b715` 已强制还原原文；`Yusha` 在
  `translator-view/protected/`（原因 `protagonist-default`）。
- 已实施：
  1. `locales/zh-CN/cmap.json` 持久化「字 → 载体码」（当前 2304 字）；
  2. 构建优先使用固化码；新字只从未使用的码追加，绝不重排旧字；
  3. 容量不足直接报错（不挤掉旧码）；当前新字形 2304/2847，余 543 格；
  4. 连续两次构建 `+0 新字`，LANG_EN/texture/cscv 哈希一致；2304 码唯一且均可在字符表反查。
- 参考：`docs/PITFALLS.md` §27、`docs/KNOWN_ISSUES.md` §13、`docs/TODO.md` T-01。
