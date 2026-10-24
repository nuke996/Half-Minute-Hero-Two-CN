# 正式版前全量漏译排查（FINAL_QA_PLAN.md）

> 状态：**进行中**（2026-10-21 记录，2026-10-22/23/24 更新，供新对话直接接续）
> 2026-10-24：Z17（`dist/Z17-display-fill/`）完成第一轮显示文本补全，并合入 Z16 视频；
> 后续实机与收尾以 **Z17** 为准；Z15 保留为回滚基线。
> 校对入口：`locales/zh-CN/translator-view/`（含 `50_extra.json`）；导入后固定刷新
> `dist/Z17-display-fill/`。

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
| 道具收藏列表 | `Mu`、`Xi` 等少数名称仍英文 | 未登记/缺译 | 先定位表与槽位，再补行 |
| 怪物图鉴第 1 项 | `Jelly` | 缺译 | 补译并全副本同步 |
| 地图编辑器 `Explanation` 栏 | 中英混排说明 | 未登记/部分缺译 | 定位该说明字段，整段翻译 |
| 合成界面 `Class Change` | 仍英文 | CSV 有译文但被保护 | 确认是纯 UI 标签后放行 |
| 合成界面 `Specialty` | 仍英文 | 未登记 | 补行 |
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

**只排查、不补全（机制名）：**

- 道具名 `Mu`（ミュー）、`Xi`（クシー）仍在道具图鉴/收藏列表显示英文；
  它们是 `b147/357/736` 的规范道具名，补译会影响按名哈希/发放，暂不动。
- 其余 `b137`（区域名）、`b656`（帝国兵）、`b290`（无限亚修/无限魔王）等
  名字类同理保留原文。
- `1,000m/h Wind` / `10,000m/h Wind`：技能名，命中 `b83/b394` 操作数，
  需走完整机制名批次，不能按说明文补。

**待后续处理（纯显示但未在本轮补）：**

- `b34` 关卡/章节标题：多数有译文但被 Q16/章节键保护，需逐条确认；
- 道具/技能说明中的能力名与发动率短句（`b147/357/736/666`）仍英文，暂未补行；
- `Catch and Release`、`Beam Security`、`Thunder Storm Breath` 等敌/技能名保持原文。

---

## 3. 排查流程（建议按顺序）

1. **以 Z17 产物为基线**：`dist/Z17-display-fill/res/LANG_EN.s2a`。
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
7. **打包**：`package_names_cn_jobs_titles_hash`，导出 translator-view 后交付实机抽检。

---

## 4. 工具与命令

```bash
# 构建当前实验包（同时刷新 dist 与校对视图）
python tools/build.py --game-dir work/original package_names_cn_reuse_z17

# 导出校对视图（含 50_extra.json）
python tools/export_review.py

# 导入校对（自检→写 CSV/extra_review.json→重建 Z17）
python tools/import_review.py

# 只读盘点（示例）
python build/_scratch/audit_untranslated_z15.py
python build/_scratch/list_blocked_display.py
```

注意：`import_review.py` 现在固定重建 Z17（`dist/Z17-display-fill/`）；不要再用旧的
`package_names_cn_jobs_titles_hash` 刷新本分支的 dist。

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

## 7. 后续 TODO：载体码（cmap）固化

> 2026-10-22 记录；尚未实施。

- 背景：`build_plan()` 按字频分配载体码，译表变化会让码整体平移；
  存档中的自定义名字是旧 CP932 字节，换补丁后会串字（尤莎→允莎）。
- 现状：主角默认名 `b391 rec2-4` 与 `b715` 已强制还原原文；`Yusha` 在
  `translator-view/protected/`（原因 `protagonist-default`）。
- TODO：
  1. 持久化某一版的「字 → 载体码」到 `locales/zh-CN/cmap.json`；
  2. 构建时优先使用固化码；新字只从未使用的码/格追加，绝不重排旧字；
  3. 容量不足时用同义词替换/拒绝新字（当前约剩 51 格），不得挤掉旧码；
  4. 连续构建两次验证同一汉字码不变，并用旧存档名字字节反查同字。
- 参考：`docs/PITFALLS.md` §27、`docs/KNOWN_ISSUES.md` §13。
