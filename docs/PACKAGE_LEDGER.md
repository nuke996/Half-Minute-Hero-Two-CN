# 实验包与回滚台账（PACKAGE_LEDGER.md）

> 目的：当实机发现“某处演出 / 技能 / 装备 / 商店 / 伙伴 / 道具异常”时，能快速判断
> 是哪个改动引入的、该修还是该回滚。
> 最近更新：2026-10-21（Z10b/Z11/Z12 + 称号守卫修复）
> 相关：`TECHNICAL.md` §10.3.7–§10.3.11、`docs/PITFALLS.md` §25.9–§25.14。

---

## 1. 基准与不可动守卫

- 母本：`work/original`（只读）；所有实验包均为隔离打包，不修改母本。
- 原始文件散列：`TECHNICAL.md` §1.1。
- **称号表 `b931`（`pos0` 名称 / `pos36` 章节标题副本）必须保持原文**：
  称号按字符串索引，翻译后“称号无法获得”（2026-10-21 实机确认）。
  该保护由 `chap_title_guard.json` 定义，现在**不受 `mirror=True` 影响**。
- Q16（勇者城）记录级保护由同一守卫 + `restore_q16_keys()` 双重保证。
- 职业/阵形/连携技表 `b128/b136/b317` 整表跳过（`skip_blobs`）。
- `b666` 内部键列 `pos288~375`：`+288` 是语言无关数字 ID，`+292` 由 Z10b+ 镜像为 `pos0`；
  两者必须按已验证配方处理。
- 名字哈希操作数：只存在于 `b83/394/417/654/756` 的 `16+rec*288+4`；
  必须按**最终写入的 CP932 载体码字节**重算（`recompute_name_operands()`），
  `JA==EN` 的内部键跳过。
- 伙伴复合键：`b954 +136`（`X Resident`）/`+168`（`X Skill`），被 `b417/b654`
  的 76 个操作数引用；`Yushia/Yuja` 随动态名保持英文。
- 脚本参数列（`b83/b394/b417/b654` 等）混有 `SE2_SKILL`/`$X`/`%s`/`100%_Fire`/`#RG` 等 token，
  **禁止整列翻译**。

---

## 2. 当前包谱系

| 包 | 构建命令 | 产物 | 内容 | 实机状态（截至 2026-10-21） |
|---|---|---|---|---|
| **stable**（E3） | `package_stable_names` | `dist/stable-names-en/` | 只写 `LANG_EN`；机制名/伙伴名/称号等保持原版；其余中文；当前译表 | **稳定基准**，历次验证可玩 |
| **Z10b** | `package_names_cn_mech_hash` | `dist/Z10b-mech-names/` | 仅技能/装备名中文 + 操作数重算；伙伴名与其余 collide 原版；**称号已恢复原版** | 序章五项、技能、装备、商店正常（2026-10-21） |
| **Z11** | `package_names_cn_partner_hash` | `dist/Z11-partner-names/` | Z10b + 伙伴名（`b954/b1034` 及全副本）+ 复合键；重算 240 个操作数 | 用户实测“尚未测出问题”；**称号已恢复原版（需复测获得）** |
| **Z12** | `package_names_cn_display_hash` | `dist/Z12-display-names/` | Z11 + 敌名/Boss 名/宝箱/音乐/地图 UI 显示列 | 敌名/Boss 说话人/音乐正常；**称号曾因 mirror 绕过守卫而变中文，已修复并重建** |
| **Z13** | `package_names_cn_batch_b_hash` | `dist/Z13-batchB/` | Z12 + 批次 B：50 个技能名（脚本参数列）+ 10 个已有译名同步 + `b99`/`b25` UI 缺译 | 伙伴技能/合成界面/元素石正常；敌人技能仍有少量漏译（Z14 已补 Chaos Wing 等） |
| **Z14** | `package_names_cn_jobs_titles_hash` | `dist/Z14-jobs-titles/` | Z13 + 职业名（12）+ 阵型名（11）+ 称号名（252）+ 新敌技名 | **尚未完整实机测试**（仅生成并完成离机校验） |
| **Z15** | `package_names_cn_reuse` | `dist/Z15-reuse-kanji/` | Z14 + **同字复用原版日文汉字槽位**（523 字，重画 527 格）；新占 2296/2847，余量 551；应用 REPL+HL；**Z15 起同步道具名全副本**，含 `stride152 pos24` 载具嵌入副本（本篇 35 / DLC 23）；**2026-10-22：DLC cmap 复用、数字 ID 保护、`force_sb` 修正**；**2026-10-23：DLC 道具/载具名同步（整槽 102 + 嵌入 23）、泳装名恢复「性感泳衣」** | **部分实机**：龙 NPC、性感泳衣已恢复；DLC 船待复测；马/摩托/越野车/竹马未逐项测。离机：主结构仅 2 处预期操作数重算、DLC 结构 0、14 类英文副本 0、嵌入副本 0、DLC 未同步 0。sha256 `LANG_EN 39297e1e3d29` / `DLC01 39a25404d9d1` |
| **Z15-norepl** | `package_names_cn_reuse_norepl` | `dist/Z15-reuse-kanji-norepl/` | 同 Z15，但**不套用 REPL**（仅保留 HL）；新增「窟」1 格，余量 550 | 对比用；未实机测试 |
| **Z17** | `package_names_cn_reuse_z17` | `dist/Z17-display-fill/` | Z15 + 显示文本补全：括号独白/选项、UI 标签（Boss/Artwork/The Usual/Robe/Swimsuit/Dress/Class Change 等）、英文多行尾行清零、`Specialty`、地图编辑器说明/半句、`b804` 萨莎日记/勋章/魔人迷宫标题、`b153` 战斗行动提示；**菜单名/分组标签全副本统一（Music Player/Craft Weapons/Gallery/Normal Mode/Best Time），修复音乐播放器购买列表闪退**；**便携女神像描述因“神→挑”字体查表问题加入 `PROTECTED_DISPLAY_OFFS`（显示原文，译文存 protected）**；**合入 Z17-video 的 4 个字幕视频（prologue/ragnarok/overture + MOV opening）**；默认「汉化-导入校对.bat」目标；**2026-10-25 修正译表两处错译（b245/2004 老管家台词、b445/63532）** | 待实机。sha256 `LANG_EN A87C91AF8452` / `DLC01 B24FDDFB15F4` / `MOV 53BD2E668E99` |
| **Z18** | `package_names_cn_reuse_z18` | `dist/Z18-dlc-place-names/` | Z17 + **DLC01 战国大陆地名汉字化**：ヒロシーマ→广岛城、アーオモリ→青森村/青森城、カッゴシマ→鹿儿岛城、オンサカ→音坂城、ニーガータ→新潟村、ワーカナイ→稚内村（含村长台词）、エーヒメ→爱媛城、ウッタエ→诉讼村、オトコテツガク→男哲学村；イー村、フクオンカ城保持原译；新增字 坂/潟/讼/哲；合入 Z17-video 的 4 个视频；默认「汉化-导入校对.bat」目标；**2026-10-27 截图校对轮**：断句重复、`AVALANCHE!` 补译、选项「尚未登场」、希腊字母/巴鲁蒙全名补全、补 `Mu/Xi`、泳装/Balmung 多行首行截断修正 | 待实机。sha256 `LANG_EN e557c6020b5d` / `DLC01 4d75992c06bc` / `MOV 53BD2E668E99`；`texture bc8e9dc75faa` / `cscv 5785a9f8ffb7`；`LANG_JA 924eff209d0e`（未改） |
| Z10（历史） | `package_names_cn_keycol_hash` | `dist/Z10-keycol-hash/` | 键列中文 + 全部名字（含伙伴名）+ 操作数 | 序章异常；仅作对照，不推荐 |
| Z4/Z6/Z7 等 | 见 `BUILDING.md` §5.5 | 各自目录 | 早期二分实验 | 历史结论已被 Z10b 修正，见 `PITFALLS.md` §25.11 |

> Z10b/Z11/Z12 在 2026-10-21 修复“`mirror=True` 连带关闭称号守卫”后已全部重建；
> 修复前三个包的 `b931 pos0` 有 191/252 条被翻成中文。

---

## 3. 症状 → 快速定位

| 现象 | 首先检查 | 处置 |
|---|---|---|
| 序章骑士不出现/不归队、贤者复活特效、魔王技能特效缺失 | 是否处于“伙伴名混合态”：`b954` 与其它副本是否同语言 | 用 Z10b/Z11/Z12（均已修）；若新包回归，回滚到 Z10b |
| 技能“有名字无效果/动画” | `b83/b394` 操作数、`b666 +288/+292`、键列 87/87 | 回滚 Z10b；检查 `recompute_name_operands` 日志（副本冲突应为 0） |
| 装备/初始装备/商店异常 | `b147/357/736/998` + `b34` loadout + `b83/b394` 操作数 | 回滚 stable/Z10b；对照 `TECHNICAL` §10.3 |
| **宝箱提示“获得××！”但背包没有** | 道具表名（`b147/357/736/998` pos4）与事件/宝箱脚本参数列（如 `b219/b290/b408` pos28）是否同串 | Z15 起 `fill_item_name_copies()` 同步全库道具名副本；旧包回滚到 Z14 也有此 bug |
| **龙/船/马等载具或 NPC 不出现**（如奇尔多尼克斯） | 道具表载具名与关卡实体表 `stride152 pos24` 是否同串（紧跟 float 尾字节 `80 BF`，无 NUL 分隔） | Z15 起嵌入副本分支同步本篇 35 处 |
| **DLC01 关卡载具不出现**（Q78 船） | DLC 的 `stride152 pos24`（`b45/b76/b97`）是否与主道具名同串 | Z15 起 `fill_dlc_item_name_copies()` 在 `refresh_dlc01` 后同步 |
| **DLC01 台词形近错字/整段乱码** | DLC 重编码是否复用主装机 cmap（`_LAST_BUILD_PLAN`） | Z15 起 `refresh_dlc01(cmap,native)` 复用主 cmap |
| **DLC 防具从装备栏消失** / 道具表 ID 成片为 0 | `_is_name_like` 是否把数字 ID 当名字；`sync_name_replicas` 是否传播空译文 | Z15 起严格 CP932 校验 + 空译文不传播 |
| **职业属性异常 / 称号条件异常** | `force_sb`：`b128` 必须 32、`b931` 必须 32 | Z15 起修正；跑 `audit_structural_changes.py` |
| 称号变中文且无法获得 | `b931 pos0` 与所有 stride292/pos32 条件副本是否同串；Q16 槽头是否完好 | 用 Z14 配方（`_TITLE_RELEASE` + `force_title_key_copies`）；旧包回滚到 Z13 |
| 职业/阵型/连携技名字部分变中文 | `b128 pos4` / `b136 pos0` / `b317 pos24/48/72` 是否被 `fill_name_copies` 写入 | 补齐必须跳过 `skip_blobs`；Z14 起职业/阵型为**有意翻译**，`b317` 仍保留原版 |
| 伙伴名错乱/不出现 | 伙伴名全副本终串是否唯一；`b954` 名字/复合键；72 个操作数 | 用 Z11+；`fill_name_copies` 补齐；检查 `b954` 是否有空行未覆盖 |
| 敌名/Boss 名异常 | `Z12_RELEASE_COLS` 几何；`b407 +4`、`b4…+92`；全副本终串 | 回滚 Z11；或拆包只保留 UI/音乐 |
| 敌人/伙伴技能名仍英文 | 是否在 `b83/b394/b417/b654 +28` 参数列；是否被 token 过滤规则排除 | 用 Z13/Z14；`Disable/Enable/Utau/Title01` 等 token 不应翻译；Z14 起称号名也已中文化 |
| 武器合成界面英文 | `b99 off16/off56`、`b25 Materials` 是否有行 | Z13 已用额外译表行补上；若回退则恢复英文 |
| 界面/物品少量漏译 | 未放行表/未登记副本 | 记为正式版前收尾项，不是回归 |
| 生僻字 `?` | 字库覆盖 / `cmap` | 检查 `build_plan` 覆盖率；不要用 `?` 判断漏译 |
| 某处文本仍是原文 | 可能受 collide/称号/Q16/键列保护 | 查 `docs/PITFALLS.md`，不要直接放行整表 |

---

## 4. 回滚与重建

```bash
# 稳定版（名字保持原版，功能优先）
python tools/build.py --game-dir work/original package_stable_names

# 机制名中文（已验证）
python tools/build.py --game-dir work/original package_names_cn_mech_hash

# 机制名 + 伙伴名
python tools/build.py --game-dir work/original package_names_cn_partner_hash

# 机制名 + 伙伴名 + 批次 A 显示名
python tools/build.py --game-dir work/original package_names_cn_display_hash

# Z15：同字复用原版日文汉字槽位（方案 B，重画简中字形）
python tools/build.py --game-dir work/original package_names_cn_reuse
```

- 安装：把对应 `dist/<包>/` 下的文件覆盖到游戏目录（先备份原文件）。
- 回滚：重新覆盖 stable 包，或用原版备份 / Steam 校验还原。
- **review 视图一致性**：任何译表/脚本改动后必须先成功 build（会自动
  `export_review.py`）；禁止导入比译表旧的 `translator-view`（`PITFALLS.md` §24）。

---

## 5. 已知未完成 / 暂不处理

- 界面少量漏译（2026-10-21 截图：道具收藏中的 `Mu`/`Xi`、怪物图鉴第 1 项 `Jelly`、
  地图编辑器 `Explanation` 栏）→ 正式版前统一全量扫描收尾。
- 武器合成界面（`b99`，stride 308）：**未登记进译表**，不是守卫/未放行问题——
  - `b99 off16` `Wooden Sword +1`（rec0 名称）无 CSV 行；
  - `b99 off56` `Combining the best features of`（说明第一行）无 CSV 行，
    第二行 `off110` 已有译文（“木刀与木棒，各取其长”）；
  - `b25 off62384/63056` `Materials: %s　＋　%s` 无 CSV 行（注意保留 `%s`）。
  **Z13 已用额外译表行补上（木剑+1 / 兼具 / 材料：%s　＋　%s），待实机验证。**
- 称号名保持原文（EN 包显示英文）——**Z14 起已改为中文**：b931 pos0 与所有
  stride292/pos32 条件副本必须同串；Q16 槽位仍按原字节恢复。
- 敌人/伙伴专属技能名、部分 Boss 名等缺译（批次 B）；脚本参数列需按内容白名单放行，
  禁止整列翻译。`Chaos Wing` 等已在 Z14 补译。
- `b892` 装备视觉部件名等未登记副本暂未放行。
- 地图编辑器机制未实测。

---

## 6. 变更记录

- **2026-10-27（Z18 截图校对轮）**：
  1. `row 14180`（`b260/18636`）跨槽台词重复：第二行原译把上一行的
     `<地震>/<落石>` 再写一遍 → 改为 `　用这些招数来攻击你吧。」`（日文该槽只写
     `攻撃してくるんじゃないかしら`）。
  2. `AVALANCHE!`（`b510/21264`，日文 `　雪崩が来よるぞ！」`）此前从未进译表，
     屏幕一直显示英文；本轮新增 `row 61303` → `　雪崩要来了！」`。
  3. `row 27053/27054`（选项 `次のうち　まだ登場していない／魔王兵器はどれか？`）
     原译丢了“まだ（尚未）”→ 改为 `「在下列选项中，` + `　哪样魔王兵器还没有登场？」`。
  4. 装备名并非槽位截断：`b713` 每条记录有 3 份名字（`pos4` 36B、`pos40` 32B、
     `pos72` 名字+说明整段），全名均放得下；屏幕上的「阿尔/贝/埃普西」来自译表与
     `ml_zh_fields.json` 首行**本身写成缩写**。本轮补全 Alpha/Beta/Delta/Epsilon/
     Iota/Omicron/Sigma/Phi/Omega/Balmung，并为 `Mu/Xi` 新增译表行
     （`b147/357/736/713` 共 8 行）。
  5. 同轮扫描发现并修正同类“说明页首行被截短”：`Sexy Swimsuit`→性感泳、
     `Balmung`→巴鲁蒙（均补成全名）；`Wood Stick`（木棒→木杖）、
     `Hero Cloth`（英雄布→英雄十字）与名字列统一。
  6. 重建 Z18（含 4 个视频），`texture/cscv` 因字频变化重新生成；
     离机自检 **error 0 / warning 45**；用打包母本 cmap 反解码 714 行
     （全部 `b713` + 本轮改动行）**逐字一致**，英文 Greek/Balmung 名整槽残留 0；
     校对视图已自动重导出（普通 55419 / 受保护 5850 / 多行 1183 / DLC 1707 / 额外 257）。
- **2026-10-24（Overture 制作人员表剧情字幕）**：
  1. 新增视频 spec `overture`（`res/LANG_EN.s2a` `a0849a33`，140.07s）：Overture 章
     制作人员表中的 13 条红色剧情独白（4.0–56.0s），**按画面英文稿翻译**
     （英文版与日文版不是逐句对应；首版按日文翻译后实机发现意义对不上，已重译）；
  2. 中文以片头同款硬字幕叠加在画面下方：红色 `#D02020`、屏显臻宋 48px、黑描边，
     不改原文、不加底框；
  3. 隔离测试包 `dist/Z17-video`（基于 `dist/Z17-display-fill`）：本轮四个字幕视频
     全部重建（`LANG_EN.s2a` 的 prologue/ragnarok/overture 三个 blob +
     `MOV.s2a` 的 opening），其余 blob 与 Z17 逐字节一致；
     未安装到母本/游戏目录。
     构建：`python tools/package_video_test.py --mode hardsub --base dist/Z17-display-fill --out-dir dist/Z17-video`。
  4. **根因（2026-10-24 实测）：** 源片是 **CFR 30fps**，静止画面靠重复帧包保持；
     普通重编码把它们折叠成 VFR（帧位少 586 个），游戏逐包推进 → 静止帧被跳过、
     过场缩短且与 BGM 不同步。而且只加 `fps=30` 仍会被 libtheora 折叠（10s 静止
     只写 28 包），因此在 `fps=30` + `tpad` + `trim` 之后再加 **2×2 暗灰块逐帧交替**
     （`drawbox 0x202020`，位于 1278,0），强制每 tick 一包。
     实测：四个视频 `missing_ticks = 0`，Overture 4214 包 / 4213 帧，
     开头 4 秒 123 包（≈30/秒）。
     新增校验：视频包数 ≥ (音频−0.3)×30、末帧 ≥ 音频−0.4s，否则构建失败。
  5. 本轮 **四个视频全部重建**（prologue/ragnarok/overture + MOV opening），
     一并修复此前所有被折叠的静止帧。
- **2026-10-24（Z17 显示文本补全）**：
  1. 括号独白/选项放行：`display_release_hit()`（以 `（` 开头且不含 Q16「勇者城」）；
  2. 逐槽放行 `DISPLAY_RELEASE_OFFS`：合成界面、战斗菜单、Change Clothes 菜单、`Specialty` 等；
  3. 日文单行/英文多行尾行（`moving.`/`ready.`/`village.` 等 8 处）补行并清零；
  4. 新增译表行：`Specialty` →「擅长」，地图编辑器 10 个 UI 标签，英文尾行用全角空格占位；
  5. `b804` 萨莎日记/勋章/魔人迷宫标题、`b291` 说明/半句、`b153` 战斗行动提示放行；
     另补 `S-I-L-E-N-C-E!`、`I have no regrets!`、`Entered tent!`、样例地图说明；
  6. Z17 自动合入 **Z17-video 的 4 个已翻译视频**（LANG_EN：prologue/ragnarok/overture；
     MOV：opening）；导入校对默认目标改为 `dist/Z17-display-fill/`；
  7. 便携女神像描述发现“描述渲染器把神解析成挑”的字体查表问题；三份描述加入
     `PROTECTED_DISPLAY_OFFS`，暂显示原文，译文保存在 protected JSON（reason=`protected-display`），
     待修复字体查表后再放行（见 `KNOWN_ISSUES.md` §22）；
  8. 修复音乐播放器购买列表闪退：`b280/1444` 分组标签未译，与已译菜单项名
     `Music Player` 不匹配；同时统一 `Craft Weapons`（b410/956）、`Gallery`
     （b280×4）、`Normal Mode`（b186/94656）、`Best Time`（b763/9872）的所有副本
     （见 `PITFALLS.md` §35、`KNOWN_ISSUES.md` §23）。
  9. **2026-10-25 译表错译修正**：
     - `row 13829`（b245/2004，`じいや「ほっほっほ ようこそおいでなすった」`）的
       `zh_new` 被误填成隔壁鲍鱼摊台词 → 改为「老管家「呵呵呵，欢迎光临」」。
       该坏行自首次提交即存在，经 `propagate_dups` 扩散到本体 LANG 中该原文的
       全部 10 个副本；与 `row 13832`（b245/2428，鲍鱼摊）撞译。
     - `row 25655`（b445/63532，`「・・・またまたぁ」`）按英文 `… Ah, well…` 误译成
       「……哎，算了……」 → 改为「……又来这套……」。
     - 重建后自检 error 0 / warning 45；sha 见上表。
  10. **2026-10-25 Z18：DLC01 战国大陆地名汉字化**：
     - 将片假名戏仿地名按现实日本地名还原：ヒロシーマ→广岛、アーオモリ→青森、
       カッゴシマ→鹿儿岛、オンサカ→音坂、ニーガータ→新潟、ワーカナイ→稚内、
       エーヒメ→爱媛、ウッタエ→诉讼、オトコテツガク→男哲学；
       `イー村`（伊村）与 `フクオンカ城`（福音香城）按用户选择保持。
     - `ワーカナイ村` 另出现在 `zh_01.tsv:69` 村长台词，已同步为「稚内村」。
     - 新增 `坂/潟/讼/哲` 4 字到 `DLC_EXTRA_CHARS`：仅追加到候选末尾，
       现有字载体码 0 变化，字库 2301/2847（余量 546）。
     - 隔离校验：所有地名槽位非空、无 `?`；未改名地名与 Z17 逐字节一致。
     - 自检 error 0 / warning 45；Z18 含 Z17-video 的 4 个视频；
       导入校对默认目标改为 `dist/Z18-dlc-place-names/`。
- **2026-10-23（Z15 补丁轮 2）**：
  1. `fill_dlc_item_name_copies()`：DLC01 道具/载具名与本篇同串（整槽 102 + 嵌入 23），
     Q78「船」修复；`refresh_dlc01()` 自动调用；
  2. 泳装译名恢复「性感泳衣」；
  3. 审计范围正式扩到 **本篇 + DLC01**（名字副本、嵌入副本、结构字段）。
  离机：DLC 未同步 0、结构主 2 / DLC 0。
- **2026-10-22（Z15 补丁轮）**：
  1. 载具名嵌入副本（`stride152 pos24`）同步 35 处 → 龙 NPC 恢复（实机确认）；
  2. `refresh_dlc01` 复用主 cmap → DLC 台词乱码修复；
  3. `_is_name_like` 严格 CP932 + 空译文不传播 → 道具 ID/装备消失修复（泳装已恢复）；
  4. `force_sb` 修正（`b128 32` / `b931 32`）→ 职业成长/称号条件 ID 不再清零（待测）。
  结构审计：主 LANG 仅 2 处预期操作数重算，DLC01 0 处。

- **2026-10-21**：Z10b 实机通过 → 机制名中文化可行；Z11 加入伙伴名/复合键并通过；
  Z12 加入批次 A 显示名；发现称号回归（`mirror` 绕过守卫），已在 `rewrite_text`
  增加 `title_guard` 并在 `fill_name_copies` 加入称号/Q16/键列跳过，三个包全部重建。
- **2026-10-21（同日第二轮）**：实机发现职业 `Hero`、阵型 `Speed Eater`、`b317`
  连携技伙伴名被部分翻译。根因 = `fill_name_copies` 未跳过 `skip_blobs(128,136,317)`。
  已修复并重建 Z11/Z12；`b128 pos4` / `b136 pos0` 恢复原版，`b317` 改动 0。
  称号获取已由用户复测通过（英文称号列表 + 可正常获得）。
- **2026-10-21（批次 B / Z14）**：Z13 新增 50 个技能名、10 个已有译名同步、4 条合成/UI 缺译；
  Z14 再翻译职业名（12）、阵型名（11）、称号名（252）及新敌技名（Chaos Wing 等），
  并发现称号的 `stride292/pos32` 条件副本必须同步，否则无法获得；
  Q16 槽头（FF 前缀）被清空的问题已修复。离机：称号 pos0 252/252、pos32 460 副本一致、
  Q16 存疑 0、操作数 242 点 0 失败。**实机待验证。**
- **2026-10-22（Z15 / 字库同字复用）**：原版 `256..1023` 中与译文同码位的 523 字
  直接沿用原版 CP932 码，不再占 `1248+` 新格；对应 527 个原版索引格重画为文泉驿简体字形。
  Z15 实测新占 2296/2847，余量 551（含复用共 2819 字）。表项 0-1247 改动 0，
  复用格像素与 `glyph3` 完全一致，操作数 242 点/冲突 0，DLC 重编码 3785 槽。
  **实机待验证。**

---

## 7. 今日新上屏文本映射表（2026-10-21）

> 用途：实机出问题时，按“现象 → 包 → 表/位置”快速定位。
> 所有坐标均指 `res/LANG_EN.s2a`（Z10b–Z14 只写 EN；JA 侧不写）。

| 包 | 文本 | 表 / 位置 | 机制与注意 |
|---|---|---|---|
| Z10b | 技能显示名 | `b666` stride376 pos0（键列 pos292 镜像同名） | `+288` 数字 ID 不动；87/87 键列校验 |
| Z10b | 装备/武器/道具名 | `b147/357/736/998` stride268 pos4（名字）；pos168/204/236（技能名副本） | 四表全副本一致；`b34` 章节 loadout 同步 |
| Z15 | 道具/装备名副本（宝箱发放） | 全库整槽同名，重点 `b219` stride196 pos28、`b290/b408` stride288 pos28、`b25`/`b218`/`b324`/`b815` 等 | `fill_item_name_copies()` 以道具表终串为准；跳过 `b128/b136/b317`、称号/Q16、技能键列 |
| Z15 | 载具/坐骑名（关卡实体） | 本篇 `stride152 pos24`：`b39/b232/b236/b429/b433/b473/b499/b556/b565/b700/b703/b803/b883/b891/b897/b938/b957/b1036/b1055` 等 | Dragon→龙、Boat→船、Horse→马、Bike→摩托、Buggy→越野车、Bamboo Stilts→竹马；`b923 "Back"` 是 token 保持英文 |
| Z15 | DLC01 道具/载具名 | `DLC01/LANG_EN.s2a`：`b45 stride152 pos24`（19 条 Boat）、`b76 rec9`、`b97 rec5`；`b32/b49/b53/b86/b94` 等 | `fill_dlc_item_name_copies()` 以主道具表终串为准，`foreign=True` |
| Z10b | 技能/装备名操作数 | `b83/394` 记录内 `16+rec*288+4` | 必须按最终 CP932 字节重算 CRC-32 |
| Z11 | 伙伴实体名 | `b954` stride288 pos4 | 42 条；`<EVO_NAME__>/<RGN_NAME__>` 保持占位符 |
| Z11 | 伙伴演员名 | `b1034` stride288 pos4 | 54 条；与 `b954` 名字集不完全一致 |
| Z11 | 伙伴复合键 | `b954` pos136（`X Resident`）/pos168（`X Skill`） | 39 条；操作数在 `b417/b654`（36+36） |
| Z11 | 伙伴名副本 | 全库整槽同名（含 `b147/357/736` 角色行、`b407` 等） | 必须全副本同串；`b317` 连携技表保持原版 |
| Z12 | 敌/怪物名 | `b407` stride236 pos4 | 916 槽；全副本补齐 |
| Z12 | Boss/敌人说话人名 | `b4/30/408/445/528/748/609/483` stride288 pos92；`b555/734` stride660 pos92 | 约 700 槽 |
| Z12 | 宝箱名 | `b777/1008` stride236 pos4 | 604 槽 |
| Z12 | 音乐名/艺术家 | `b320` stride492 pos228/292 | 238 槽 |
| Z12 | 地图编辑器 UI | `b715` stride224 pos112 | 232 槽 |
| Z13 | 技能/喊话/曲名 | `b83/394/417/654/408/445/748` stride288 pos28 | 内容白名单；排除 `Disable/Enable/SE2_SKILL/$X/%s` 等 token |
| Z13 | 武器合成 UI | `b99` stride308 off16（名称）/off56（说明首行）；`b25` off62384/63056（`Materials: %s　＋　%s`） | 原缺译表行；Z13 起补 |
| Z14 | 职业名 | `b128` stride212 pos4 | 12 条；`pos84` 说明文由 `desc_release` 翻译 |
| Z14 | 阵型名 | `b136` stride272 pos0 | 11 条；`pos64` 说明文由 `desc_release` 翻译 |
| Z14 | 称号名 | `b931` stride292 pos0；条件副本 `stride292` 表 **pos32** | 252 条；pos32 460 副本必须同串；`pos36` 章节标题保持原版 |
| Z14 | 新敌技名 | `b483/528/609` stride288 pos28（及同名列） | Chaos Wing→混沌之翼 等 |
| Z14 | 主角默认名 | `b391` stride168 pos40 rec2/3/4（Yusha/Yushia/Yuja）；`b715` off18272 | **强制还原原文**，保证旧存档名字不串字；校对视图归入 `protected/` |
| 全包 | 名字哈希操作数 | `b83/394/417/654/756` `16+rec*288+4` | `JA==EN` 为内部键跳过；其余按最终字节重算 |

**不动的表：** `b128/b136` 的描述列只由 `desc_release` 翻译；`b317` 连携技整表保持原版；
`b931 pos36` 章节标题副本保持原版；Q16 记录按原字节恢复。

---

## 8. Q16「勇者城」复核（只记录，本轮不修改）

**结论：属于同一大类（按名/按字符串键），但不是 CRC 操作数问题。**

- Q16 的字符串（`勇者城` / `Hero Castle`）在 `LANG` 的特定记录里是**精确字符串键**，
  `cscv` 侧有逐字节孪生。翻译任一侧都会导致按名匹配失败 → 选关后勇者城消失。
- 修复方式不是重算哈希，而是 `restore_q16_keys()`：把相关槽位逐槽写回
  **该文件自己的原版字节**（日文侧日文、英文侧英文）。
- 与 Z10b–Z14 的名字问题对比：
  - 相同：都是“字符串本身是键 + 多副本必须一致”；
  - 不同：Q16 是**直接字符串比较**、无 32 位 CRC 操作数；Z10b–Z14 的名字走
    `名称→CRC-32→比 u32`，需要 `recompute_name_operands()`。
- 2026-10-21 Z14 发现：批量补齐曾把 Q16 槽头的 `FF FF FF FF` 前缀清零；
  已让 `restore_q16_keys()` 在“live 槽头为空且长度不越记录边界”时直接写回原字节，
  复验 Q16 存疑 0。
- 参考：`docs/PITFALLS.md` §11、§25.17；`TECHNICAL.md` §10.3.12。

---

## 9. 校对 / 导入 / 打包入口（2026-10-21 起）

- `locales/zh-CN/translator-view/` 已支持今日新上屏文本：
  - `text_v2.csv` 中已有的行（职业/阵型/称号/敌名/音乐/地图 UI 等）：
    即使 `apply_menu` 仍判为保护，也按已放行槽位导出到普通分片，可直接改 `zh`；
  - 不在 CSV 的代码内额外行（伙伴名/复合键/技能名/合成 UI）：
    导出为 `50_extra.json`，id 形如 `extra::<blob>::<offset>`；
  - 导入时额外行写入 `locales/zh-CN/extra_review.json`（完整覆盖表），
    CSV 行写回 `text_v2.csv`；
  - `汉化-导入校对.bat` 自检通过后固定运行
    `package_names_cn_reuse` 刷新 `dist/Z15-reuse-kanji/`（应用 REPL+HL）；
  - `汉化-导入校对-不应用词典.bat` 运行 `import_review.py apply --no-repl`，
    重建 `dist/Z15-reuse-kanji-norepl/`（不套用 REPL，仅保留 HL）；
    两者读同一批 JSON，只是打包模式不同；
  - 对应装机：`汉化-安装.bat`（应用 REPL）/ `汉化-安装-不应用词典.bat`（仅 HL）；
  - 回滚会同时恢复 `extra_review.json` 与 `text_v2.csv` 的备份。
- 已实测：导出 55,170 普通 / 6,048 受保护 / 1,181 多行 / 1,707 DLC / **257 额外**；
  导入无改动时 0 修订；改 1 条额外译文（兼具→兼备）后成功写入并重建包
  （Z14 时期重建 Z14，Z15 起重建 Z15）。

---

## 10. Z14 测试状态（重要）

- **Z14 尚未完整实机测试**：目前只完成生成与离机校验（职业 12/12、阵型 11/11、
  称号 252/252、pos32 460 副本一致、Q16 存疑 0、操作数 242 点 0 失败）。
- 2026-10-22 追加：主角默认名 `b391 rec2-4` 与 `b715` 已强制还原原文
  （`restore_protagonist_defaults()`），`Yusha` 在 `translator-view/protected/`；
  重建后 4 处默认名均为原版，操作数 260 点 0 失败。
- 需要实机覆盖：职业切换/职业装备、阵型效果、称号获得、Q16 勇者城、Chaos Wing 等敌技、
  以及此前已通过的序章/技能/装备/商店/伙伴/敌名/音乐。
- 若出现问题：优先回滚到 Z13；称号单独失败时先对比 `b931 pos0` 与 pos32 副本。

---

## 11. 机制名副本全面审计（2026-10-22/23，Z15）

**脚本：** `build/_scratch/audit_mechanic_replicas.py`（本篇 14 类 + DLC01）与
`build/_scratch/audit_structural_changes.py`（本篇 + DLC01 结构字段）。

**14 类机制名（当前全部英文副本 0）：** skill 85 / item 633 / partner 42+52+36 /
class 12 / formation 11 / title 252 / enemy 611 / boss_speaker 313 / chest_label 497 /
music 51 / map_ui 262 / script_name 76。
剩余“变体”仅为引号台词/风格差异；显示类重名 enemy 17 / chest 23 / map_ui 1，
其哈希在操作数 blob 与 `cscv` 中 0 命中。

**嵌入副本：** 本篇 `stride152 pos24` 未同步 **0**；DLC01 整槽+嵌入未同步 **0**。

**按名哈希碰撞：** 被操作数引用的同哈希 3 组，全部是技能/道具**跨表同名**：
英雄十字（Hero Cross/Hero Cloth）、战斧（Tomahawk/Battle Axe）、召唤（Summon/召唤道具）。
第一组在日文母本中本来就叫 `ヒーロークロス`（同串同哈希），原版可运行 ⇒ 引擎按表解析，
跨表同名安全；其余两组结构相同。同一类别内部重复译名 0。

**结构改动基线：**
- 主 LANG：仅 **2 处**预期改动（`b83/b394 rec196/824` 名字哈希操作数重算）；
- `DLC01/LANG_EN`：**0 处**结构性改动。

**结论：** 本篇 + DLC01 的机制名副本、嵌入载具名、结构字段均已静态度量通过；
龙 NPC 与泳装已实机恢复。剩余实机项见 `docs/FINAL_QA_PLAN.md` §2.1。
