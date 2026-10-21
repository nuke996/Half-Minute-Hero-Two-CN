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
| **Z14** | `package_names_cn_jobs_titles_hash` | `dist/Z14-jobs-titles/` | Z13 + 职业名（12）+ 阵型名（11）+ 称号名（252）+ 新敌技名 | 待实机验证 |
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
