# 构建说明（BUILDING.md）

本文档描述如何从"干净的仓库 + 用户自备的正版游戏文件"重建本汉化。

> 现状说明（2026-10-05 更新）：仓库 `tools/` 版本**已解除硬编码路径**（改用 `tools/paths.py` +
> `config.local.json` / 环境变量），并已完成一次**干净目录构建验证**：以自备原版游戏文件 +
> `python tools/build.py --game-dir <dir> apply_menu` 可复现产出补丁，两次构建**逐字节一致**，
> `revert` 可还原。详见文末 §15「构建验证记录」。

---

# 1. 支持的原始游戏版本

| 项 | 值 |
|---|---|
| 游戏 | Half Minute Hero Two（勇者30：再次降临） |
| 平台 | Steam PC / Windows（x86） |
| 发行 | Steam |
| 可执行文件 | `HMH2.exe`（1,985,536 字节，无 PE 版本资源） |
| 校验（原版） | SHA-256 前 16 = `1A313A50319BD5FE`，MD5 前 12 = `867308FCD87A` |

原版母本散列基准见 `TECHNICAL.md` §1.1。**不同 Steam 更新/区域版本应视为不受支持**，
补丁工具在写入前应校验字节数/散列，不匹配即中止。

---

# 2. 前置条件

| 依赖 | 说明 |
|---|---|
| 操作系统 | **Windows**（构建脚本使用 `ctypes` 调用 GDI，无法在 Linux/macOS 上完成 SimSun 回退路径） |
| Python | **3.13（64 位）**；脚本无版本断言 |
| Pillow | `pip install pillow`（渲染字模、读写 8bpp 调色板 BMP 图集） |
| 字体 | `WenQuanYi Bitmap Song 13px.ttf`（文泉驿点阵宋体，GPL-2.0，仓库自带于 `assets/fonts/`） |
| 可选工具 | `zig` 工具链（仅在需要重建 `dinput8` 代理 DLL 时用到） |

字体：构建默认读取仓库内 `assets/fonts/WenQuanYi Bitmap Song 13px.ttf`
（可用 `HMH2_FONT_PATH` 或 `config.local.json` 的 `font_path` 覆盖）；
缺失时**不报错**，回退 GDI SimSun 16px 单色（无描边，观感下降）。
另可覆盖渲染参数：`HMH2_FONT`（`wqy12/wqy13/wqy14/wqy16/simsun`）、`HMH2_THICK`、`HMH2_OUTLINE`。

---

# 3. 原始游戏文件（用户自备）

本项目**不包含**任何游戏本体文件。构建需要用户自备（Steam 正版）：

```text
HMH2.exe                    # 原版可执行（构建会优先以 HMH2.exe.bak 为母本）
res/LANG_JA.s2a             # 日文文本
res/LANG_EN.s2a             # 英文文本
res/cscv.s2a                # 脚本 + 字形字符表
res/texture.s2a             # 字形图集
DLC01/LANG_JA.s2a           # DLC01（可选）
DLC01/LANG_EN.s2a           # DLC01（可选）
DLC01/res.s2a               # DLC01（可选）
```

**[已验证] 首次构建会自动备份**：`apply` 开始时若目标存在而 `.bak` 不存在，则复制为 `.bak`。
但**必须先有原始母本**（尤其是 `HMH2.exe.bak`），否则 exe 补丁会中止。

> **[已验证] DLC01 也会自动备份**：当 `DLC01/LANG_JA.s2a`、`DLC01/LANG_EN.s2a` 存在时，
> `refresh_dlc01` 会在备份缺失时由当前文件自动生成 `*.bak_dlc01_20260913`；未持有 DLC 的玩家
> 不会创建任何 DLC01 文件。因原件备份取自"当前文件"，**应在原版状态下首次运行**
> （对已装机的目录运行会把已改内容误当原件，此时 `package_install` 的逐文件校验会拒绝并中止）。

---

# 4. 目录准备与路径配置

**[已验证] 仓库 `tools/` 内的脚本已按规范解除硬编码**：路径由 `tools/paths.py` 统一解析，
优先级为 **环境变量 > `config.local.json` > 仓库内相对默认值**。

配置方式（任选其一）：

1. 复制 `config.example.json` 为 `config.local.json`，填入 `game_dir`（游戏安装目录；**绝对路径或相对仓库根的相对路径**均可）：
   ```json
   { "game_dir": "work/original", "locale": "zh-CN" }
   ```
   官方原版可放在仓库内 `work/original/`（该目录已被 `.gitignore` 忽略），此时 `game_dir` 写相对路径 `work/original`。
2. 运行时指定：
   ```bash
   python tools/build.py --game-dir "D:\\Games\\Half Minute Hero Two" apply_menu
   # 或 set HMH2_GAME_DIR=D:\Games\Half Minute Hero Two
   ```

`game_dir` 需包含原版 `HMH2.exe`、`res/`、`DLC01/`。`game_dir` / `data_dir` / `build_dir` / `dist_dir` /
`font_path` 均支持"绝对路径或相对仓库根的相对路径"。字体默认取 `assets/fonts/WenQuanYi Bitmap Song 13px.ttf`。

> 说明：作者早期工作目录 `_work/` 已不在本仓库中（其脚本曾保留硬编码 BASE）。
> 现行仓库只有 `tools/` 版本，为对外可复现、可重定位（relocatable）的规范版本。

---

# 5. 构建入口

## 5.1 统一脚本入口

```bash
python tools/runner.py <脚本名> [参数]
```
（在仓库根或 `tools/` 内运行；脚本在 `tools/` 下执行，工具输出统一写入 `build/`，
如 `build/<脚本名>_run.txt`。）

## 5.2 主构建器 `build_cn.py`（经 `tools/build.py` 调用）

统一入口：`python tools/build.py [--game-dir DIR] [--exe-mode dll|exe] <命令>`。
默认 `--exe-mode dll`（运行时代理 DLL，磁盘 `HMH2.exe` 保持原版）；离线改写 exe 用 `--exe-mode exe`。
命令含义如下：

| 命令 | 作用 |
|---|---|
| `python tools/build.py plan` | 统计覆盖率/拟装字数，**不改文件** |
| `python tools/build.py apply` | 默认参数构建安装（text+sync_cscv+keep_collide+skip MECHANIC_BLOBS） |
| `python tools/build.py apply_menu` | **生产装机**：apply + 自动刷新 DLC01 + Q16 键名保护 |
| `python tools/build.py revert` | 从 `.bak` 还原全部文件（不含 DLC01；DLC 用 `dlc_apply.py revert`） |
| `python tools/build.py check` | 打印各文件"原版/已修改"及 SHA-256 前 12 位 |
| `python tools/build.py dlc_only` | 只按当前字库重编码 DLC01 |
| `python tools/build.py [--game-dir "<游戏目录>"] package` | **完整补丁打包（默认·隔离）**：只读游戏目录里的原版文件（优先 `*.bak`，缺失时退回同名当前文件，如干净原版目录 `work/original`），在 `build/package_stage/` 里装机并校验各文件"确实与原件不同"，再按相对路径把补丁文件集复制进 `dist/`（不打 zip）。**游戏目录逐字节不变（不装机）**；缺原版文件时明确中止 |
| `python tools/build.py [--game-dir "<游戏目录>"] package_install` | **就地装机版打包**：对游戏目录跑 `apply_menu`（会把目录留在已汉化态）→ 校验 → 复制到 `dist/`。`DLC01` 仅在游戏目录确实存在原件时纳入（其原件备份自动生成）。`package_exe` / `package_install_exe` 为对应的 exe 模式 |
| `apply_font` / `apply_nosync` / `apply_nocollide` / `apply_consistent` / `apply_nomech` | 历史测试包 A/B/C/E/D |
| `apply_noplace` / `apply_menu_safe` / `apply_menu_noml` | 变体（回退地名/保守 UI/退回单行） |

## 5.3 一键 `.bat`（由 `make_bats.py` 生成）

`tools/make_bats.py` 把入口 bat 生成到两处：

- **装机类** → 游戏目录（`game_dir`，默认 `work/original`；该目录不入版本控制）
- **校对类（导出 / 导入 / 回滚）** → `locales/<locale>/translator-view/`，
  与面向译者的校对 JSON 同目录，随仓库一起分发，译者不依赖游戏目录

| bat | 位置 | 调用 |
|---|---|---|
| `汉化-安装.bat` | 游戏目录 | `build_cn.py revert` -> `build_cn.py apply_menu` |
| `汉化-还原.bat` | 游戏目录 | `build_cn.py revert` |
| `汉化-导出校对.bat` | `locales/<locale>/translator-view/` | `export_review.py` |
| `汉化-导入校对.bat` | `locales/<locale>/translator-view/` | `import_review.py apply` |
| `汉化-导入校对-回滚.bat` | `locales/<locale>/translator-view/` | `import_review.py revert` |

两个位置的 bat 都用 `..\..` / `..\..\..` 相对路径指向 `tools/`，且都依赖
`config.local.json` / 环境变量定位游戏目录与译表，故放在哪一层都能跑。
另有大量历史/专项 bat（健康体检、说明文放行开关、Q16 键名保护开关等），
由 `tools/make_bats.py` 定义并一并生成到游戏目录。

## 5.4 校对（导出 / 导入 / 回滚）

面向译者的校对链路由三个脚本（`tools/export_review.py`、`tools/import_review.py`、
共用库 `tools/review_lib.py`）驱动；入口 bat 与 JSON 同在 `translator-view/`：

- **导出**：`export_review.py` → `locales/zh-CN/translator-view/`，按 blob 切分成
  `10_ui_*.json` / `20_dialogue_*.json`，外加 `30_multiline.json`、`40_dlc01.json`、
  `protected/`（受保护、当前不上屏）、`dict/替换词典.json`（快照）与 `如何校对.txt`。
  清理旧产物时只删上面这些生成物（`10_*` / `20_*` / `30_*` / `40_*` / `protected/` /
  `dict/`），**保留同目录的 `.bat`**，所以导出 bat 与 JSON 可以长期共处一目录。
  受保护判定复用生产装机口径：脚本把原版复制到 `build/review_stage/` 作只读母本，
  临时切换 `build_cn.BASE` 后调用 `rewrite_text(..., dry_run=True, classify=...)`。
- **导入**：`import_review.py apply` → 逐条比对 `zh` → **自检**（超长/id/非法字符）……
  有任一错误即**中断**：不写译表、不打包，写 `build/校对/导入报告.txt` 指明问题条目；
  通过后备份（`*.bak_review_<ts>`）→ 写回 `text_v2.csv` / `ml_zh_fields.json` / DLC 译表
  → 自动跑 `tools/build.py package`（隔离模式）刷新 `dist/`，**不改游戏目录**。
- **回滚**：`import_review.py revert` → 从 `build/校对/_import_state.json` 记录的备份还原
  译表，并重新刷新 `dist/`。
- **打包后强制导出（硬规则）**：`package` / `package_install`（含 `*_exe`）在写完 `dist/`
  后会自动运行 `export_review.py` 刷新 `translator-view/`；导出失败则以非零码退出并提示，
  在手动导出成功前**不得**运行导入校对。原因见 `docs/PITFALLS.md` §24：旧视图会把旧译文
  整体回写译表。**任何译表或汉化脚本改动，都必须以一次成功打包（即自动导出）收尾。**

---

## 5.5 名字本地化实验包（保留，用于对照与后续探索）

以下命令均为**隔离打包**（只读母本目录，不修改游戏目录），产物写入 `dist/`：

| 命令 | 产物 | 配方要点 |
|---|---|---|
| `package_lang_en_names_en` | `dist/E3-lang-en-names-en/` | **E3 · 最稳定，必须保留**：只写 `LANG_EN`，机制名保持原版英文，其余中文 |
| `package_stable_names` | `dist/stable-names-en/` | **稳定版备份**：与 E3 同配方，固定输出到独立目录；用当前译表/字库构建，不会回退后续新译文。需要"随时回到可玩稳定状态"时用它，不影响默认 `dist/` |
| `package_lang_ja_names_ja` | `dist/E3-ja-lang-ja-names-ja/` | **E3-JA**：E3 的日语镜像 —— 只写 `LANG_JA`，机制名保持原版，其余中文（游戏语言须设为**日语**） |
| `package_names_cn_skill_loadout` | `dist/Z4-skill-loadout/` | **Z4**：技能/装备名中文 + 章节 loadout 值同步 + 武器表副本同步；`b666 +292` 键名保持原版 |
| `package_names_cn_skill_loadout_ja` | `dist/Z4-ja-skill-loadout/` | **Z4-JA**：Z4 的日语镜像（只写 `LANG_JA`；`+292` 保持该文件原版日文）。**实机验证：与 Z4 同样异常**，仅作对照保留 |
| `package_names_cn_skill_only` | `dist/Z3-skill-only/` | 二分对照：同 Z4 但不改 loadout（用于定位"装备丢失"） |
| `package_names_cn_skill_only2` | `dist/Z6-skill-only2/` | 二分对照：只翻技能名，装备名保持英文 |
| `package_names_cn_equip_only` | `dist/Z7-equip-only/` | 二分对照：只翻装备名，技能保持英文 |
| `package_names_cn_keycol` | `dist/Z9-keycol/` | 反证实验：把 `b666 +292` 键名也翻中文（**已验证不可用**，技能有名字无效果） |
| `package_names_cn_mech_hash` | `dist/Z10b-mech-names/` | **Z10b 判别包**：其余 collide/伙伴名保持 stable 原样，仅技能/装备名中文化 + 操作数重算；伙伴名最后强制回写原版 |
| `package_names_cn_partner_hash` | `dist/Z11-partner-names/` | **Z11**：Z10b + 伙伴名（b954/b1034 及全部副本）+ b954 `X Resident`/`X Skill` 复合键；重算 240 个操作数（含 72 个复合键引用） |
| `package_names_cn_display_hash` | `dist/Z12-display-names/` | **Z12 批次 A**：Z11 + 敌名/Boss 名/宝箱/音乐/地图 UI 等已有译文的显示列；称号表按守卫保持原文 |
| `package_names_cn_batch_b_hash` | `dist/Z13-batchB/` | **Z13 批次 B**：技能名/合成 UI 缺译；脚本参数列按内容白名单 |
| `package_names_cn_jobs_titles_hash` | `dist/Z14-jobs-titles/` | **Z14**：Z13 + 职业/阵型/称号名 + 新敌技名；称号连同 pos32 条件副本同步 |

用法示例：

```bash
python tools/build.py --game-dir work/original package_names_cn_partner_hash
python tools/build.py --game-dir work/original package_names_cn_display_hash
```

> 各包内容、实机状态、症状定位与回滚方式见 `docs/PACKAGE_LEDGER.md`。

> **默认打包行为 = HEAD（`9d8299b`）生产配方。**
> `python tools/build.py --game-dir work/original package`（以及 `package_install`）
> 仍按 HEAD 的 `apply_menu` 配方执行：双侧 `LANG` 写入 + `cscv` 同步 + place/chap/song。
> 已实测其产物与 `dist/HEAD-package/` **8 个文件逐字节相同**。
> E3 / Z4 等隔离配方不受影响，通过上表各自的命令调用。

结论与失败教训见 `TECHNICAL.md` §10.3 与 `docs/PITFALLS.md` §25；
当前可用包与已知缺陷见 `docs/KNOWN_ISSUES.md` §10.1。

### 5.5.1 日语包与英语包的区别（重要）

两者的**配方完全对称**，但底层条件不同：

| 项 | 英语包（写 `LANG_EN`） | 日语包（写 `LANG_JA`） |
|---|---|---|
| 槽位基准 | 行偏移以 **`LANG_JA`** 为基准计算，再套用到 EN | **原生基准**（`lang_a` 就是 JA），对齐最稳 |
| 未参与侧 | `LANG_JA` + `DLC01/LANG_JA` 逐字节不动（断言强制） | `LANG_EN` + `DLC01/LANG_EN` 逐字节不动（断言强制） |
| `cscv` | 保持原版（仅重写字符表 blob） | 同左 |
| DLC01 | `refresh_dlc01(en_only=True)` | `refresh_dlc01(ja_only=True)` |
| Q16 键名 | 按 TSV 的 `file` 字段自动分文件回写 | 同左（无需改） |
| 游戏内语言 | 必须设为 **English** | 必须设为 **日本語** |

**主要风险（日语包特有）：**

1. **`cscv` 与 `LANG_JA` 天然是"孪生"关系**（项目实测 653~687 个 blob 曾逐字节相同）。
   日语包把 `LANG_JA` 改成中文、而 `cscv` 保持日文原版，**打破的正是这对孪生**；
   英语包不存在这个问题（`LANG_EN` 与 `cscv` 本来就不是一套）。
   → 因此日语包**更需要实机回归**，尤其注意历史事故点：勇者城、章节名、称号、伙伴名、技能效果。
2. **语言切换会改变读取的文件**：同一份存档在 EN/JA 之间可通用（已实测），
   但补丁只覆盖一侧，另一侧仍是原版 —— 切到未打补丁的语言会看到原版文本（属预期）。
3. `refresh_dlc01(ja_only=True)` 只重编码 `DLC01/LANG_JA.s2a`；
   若玩家未持有 DLC，目录保持干净（不创建文件）。
4. 载体码 `cmap` 按**全量字频**分配，与写入哪一侧无关；因此 EN/JA 两个包的
   字体与字符表产物相同，可互相复用。

---

# 6. 推荐构建管线

**[已验证]** `汉化-安装.bat`（= `revert` + `apply_menu`）实际执行：

```text
0) 若缺 .bak 则自动备份（HMH2.exe / LANG_JA / LANG_EN / cscv / texture）
1) exe：从 HMH2.exe.bak 还原；若 UNLOCK_1280 则 patch_exe_unlock() 打离线补丁
2) rewrite_atlas_cscv()：
     读 texture.s2a.bak + cscv.s2a.bak
     -> 以 WenQuanYi 渲染全部候选字 -> 重画图集 A/B
     -> 重写字符表 blob（扩容到 4096，写头[8]=256）
     -> 写回 texture.s2a / cscv.s2a
3) rewrite_text()：
     读 LANG_JA.s2a.bak + LANG_EN.s2a.bak
     -> 按 text_v2.csv 改写 LANG_JA / LANG_EN
     -> cscv 内容匹配同步（跳过键名字段）+ 显式孪生表（CSCV_CHAP_JOBS）
     -> apply_cscv_place()（村落名 cscv[28]）
     -> apply_song_lyrics()（小咕之歌 cscv[355] 英文行）
4) refresh_dlc01()：按当前字库重编码 DLC01
5) restore_q16_keys()：Q16 键名槽位写回该文件自己的原版字节
```

> 当前磁盘 `HMH2.exe` 等于原版（采用 `dinput8` 运行时方案），则第 1 步等价于"保持原版"。

---

# 7. 版本校验与失败行为

- **[已验证]** exe 补丁逐条校验期望原字节（`0x81 0xFF ...` 等），任何一处不匹配即 `SystemExit` 中止；
  若 exe 已含 `.atbl` 节也直接拒绝（要求先 revert）。
- **建议补充**：构建前对用户提供的原版做 SHA-256 校验（对照 `TECHNICAL.md` §1.1），
  当前脚本对 `res/*.s2a` **没有**做散列校验（仅按结构解析），这是可复现性/安全性上的缺口。

---

# 8. 构建输出

- **就地装机**（`apply` / `apply_menu`）会把补丁产物直接写入游戏目录：`HMH2.exe`、
  `res/LANG_JA.s2a`、`res/LANG_EN.s2a`、`res/cscv.s2a`、`res/texture.s2a`
  （+ DLC01 的 `LANG_JA.s2a`、`LANG_EN.s2a`；DLC01 `res.s2a` 不改写）。
- **工具运行产物**（日志 `*.txt`、`collide_cache.json`、回滚/快照备份 `_pre_*/`、`_name_good/`、
  校对工作目录 `校对/`、`存档记录.md` 等）统一写入仓库 `build/`（定义见 `tools/paths.py`），
  与语言数据目录 `locales/zh-CN/` 严格分离。`build/` 已被 `.gitignore` 忽略。
- `dist/` 用于**完整补丁打包**：
  - `python tools/build.py [--game-dir "<游戏目录>"] package`（**默认·隔离**）：只读游戏目录里的
    原版文件（优先 `.bak`，缺失时退回同名当前文件），在 `build/package_stage/` 里装机并校验，
    再复制到 `dist/`；**游戏目录逐字节不变**。
  - `python tools/build.py [--game-dir "<游戏目录>"] package_install`：旧行为——对游戏目录
    **就地装机**（目录会变为已汉化态）后再复制到 `dist/`。
  - 两者产物一致：可直接覆盖到游戏目录的补丁文件集（dll 模式 = `dinput8.dll` + `hm2zh_patch.bin`
    + `res/*.s2a`(4) + `DLC01/*.s2a`(2)〔后者仅在游戏目录确实存在 DLC01 母本时纳入〕；
    exe 模式 = `HMH2.exe` + 同 6 个 s2a），按相对路径写入。
  - 注意 payload 就是整份 s2a（**约 320 MB**），命令只做复制、不压缩、不自动打 zip，
    也不会删除 `dist/` 中不属于本次补丁的旧文件。隔离模式的 `build/package_stage/` 可随时删除。
- 还原命令：`python tools/build.py revert`（从 `.bak` 覆盖回原文件）。

---

# 9. 可复现性现状

| 项 | 现状 | 结论 |
|---|---|---|
| exe 补丁 | 逐条校验原字节；离线与运行时两条路径等价 | **可复现** |
| 图集/字符表生成 | 从 `.bak` + 字体确定性生成 | **可复现**（依赖字体文件） |
| 文本导入 | 从 `text_v2.csv` + 守卫 JSON 确定性导入 | **基本可复现** |
| 游戏根路径 | 由 `tools/paths.py` 解析（环境变量 > `config.local.json` > 仓库相对默认） | **可复现**（已解除硬编码） |
| 字形字体 | 默认读仓库 `assets/fonts/`（可被 `HMH2_FONT_PATH` 覆盖）；缺失静默降级 | **基本可复现**；缺失时仍缺"报错" |
| 构建输入 | 语言数据在 `locales/<locale>/`；缓存/中间产物在 `build/` | **可复现** |
| `collide_cache.json` | 缺失时现场重算（很慢） | 可重建但耗时 |
| 输出 | 工具产物统一写入 `build/`；发布产物写入 `dist/` | 符合规范 §22 |
| 母本校验 | `res/*.s2a` 无散列校验（仅 exe 逐条校验原字节） | **应补充** |

**仍待补充（建议）：**
1. 增加 `validate_inputs`：对原始 `HMH2.exe` / `res/*.s2a` 做散列校验（对照 `TECHNICAL.md` §1.1）。
2. 构建入口尚未完全参数化 locale（当前以 `zh-CN` 为准，见 `TRANSLATING.md` §16）。
3. 字体缺失时应**报错**而非静默降级。

---

# 10. 校验与体检命令

```bash
python tools/build.py check                   # 各文件 原版/已修改 + 散列
python tools/t34_health.py                    # 项目体检，exit 0=全绿
python tools/t162_diff_audit.py <备份根> <批次id...>   # 零附带变化审计
python tools/t152_verify_g1.py                # 功能级反解（批次示例）
python tools/dlc_apply.py verify              # DLC01 三重验证
```

---

# 11. DLC01 独立流程

```bash
python tools/dlc_export.py            # 导出工作单（只读）
python tools/dlc_apply.py plan        # 生成写入计划
python tools/dlc_apply.py apply       # 写入（超容量即中止）
python tools/dlc_apply.py verify      # 三重验证（读回 / 无越界清零 / 记录尾一致）
python tools/dlc_apply.py revert      # 从 *.bak_dlc01_20260913 还原
```

**[已验证]** DLC01 写入只在自己原文占用范围内改写，绝不越界清零（v1 曾把记录尾清零导致剧情断链）。

---

# 12. 代理 DLL（运行时补丁）构建

```text
tools/proxydll/main.c            # 代理 DLL 源码
tools/proxydll/dinput8.def       # 导出表
tools/proxydll/gen_patch_bin.js  # 由 HMH2.exe.bak 生成 hm2zh_patch.bin（含自测）
tools/proxydll/build.bat         # 构建脚本（zig 工具链 + fix_exports.js）
tools/proxydll/fix_exports.js    # 去除导出名 @N 装饰（原位截断）
tools/proxydll/check_dll.js      # 校验 machine / 导出 / 导入
```

构建：`set ZIG=<zig.exe 路径>` 后运行 `build.bat`（或把 zig 放进 PATH）。
zig 0.13 实测两点：目标三元组为 `x86-windows-gnu`（`i686-...` 已不被接受），
且 zig 的 lld 不支持 `--kill-at`，所以 build.bat 编译后再用 `fix_exports.js`
把 `Name@N` 装饰名原位截断为未装饰名（游戏按未装饰名导入）。

产物部署到游戏根目录：`dinput8.dll` + `hm2zh_patch.bin`。
`gen_patch_bin.js` 会把补丁虚拟应用到 `HMH2.exe.bak` 并与当前 `HMH2.exe` 的 `.text` 区逐字节比对作为自测。

---

# 13. 常见故障

| 症状 | 原因 | 处理 |
|---|---|---|
| `缺少 HMH2.exe.bak，无法打补丁` | 缺原版母本 | 提供原版 exe 并备份为 `.bak` |
| 找不到 `res/...` 文件 | `game_dir` 解析不对 | 用 `--game-dir` / `HMH2_GAME_DIR` / `config.local.json` 的 `game_dir` 指定游戏目录 |
| 字模变细/无描边 | 未找到 WenQuanYi，回退 GDI SimSun | 确认仓库 `assets/fonts/` 字体存在（或设 `HMH2_FONT_PATH`） |
| `! exe 已含 .atbl 节` | 对已打补丁的 exe 再次打补丁 | 先 `revert` |
| 构建后文字显示为别字 | 改了 `text_v2.csv` 但未重装 DLC01 | 跑 `apply_menu`（含 DLC 刷新） |
| `python` 无法执行 | 解释器不在 PATH | 用完整 python 路径或 `runner.py` |

更多历史故障见 `docs/PITFALLS.md`。

---

# 14. 分发

- **成品式（推荐，零依赖）**：
  - DLL 模式（默认）：分发 `dinput8.dll` + `hm2zh_patch.bin`（`HMH2.exe` 保持原版）+ `res/texture.s2a`、
    `res/cscv.s2a`、`res/LANG_JA.s2a`、`res/LANG_EN.s2a`。
  - exe 模式：分发已打补丁的 `HMH2.exe` + 4 个 `res/*.s2a`。
  - 两者都无需玩家安装 Python/字体/`.bak`。
- **脚本式**：需玩家自备游戏、安装依赖、改 `BASE` 路径、安装字体；仅适合开发者。
- Steam 校验完整性会还原被改文件（exe 与资源），属预期行为。


---

# 15. 构建验证记录（2026-10-05）

在**干净目录**中验证（不触碰正在运行的游戏安装）：

```text
前置：从一个游戏安装导出"原版"文件到临时目录（HMH2.exe 与 res/*.s2a、DLC01/*.s2a 均取原版母本）
仓库：将 Half-Minute-Hero-Two-CN 复制到另一临时目录（可重定位，路径与作者机器无关）
执行：python tools/build.py --game-dir <临时游戏目录> plan
      python tools/build.py --game-dir <临时游戏目录> apply_menu
```

结果：

- `plan`：CSV 60798 行，覆盖率 100.07%，未覆盖字 0，exit 0。
- `apply_menu`（默认 DLL 模式）：磁盘 `HMH2.exe` 保持原版；生成/部署 `dinput8.dll` + `hm2zh_patch.bin`；
  图集重画为 512×1024，字符表 1424→4096 项，
  LANG 各写入 49568 处，cscv 孪生同步，DLC01 重编码 3785 槽，Q16 键名写回 183 处，exit 0。
- **确定性**：连续两次 `apply_menu`，7 个产物文件（exe + 4×res + 2×DLC）SHA-256 **全部一致**。
- **可还原**：`revert` 后 5 个主文件与原版母本逐字节一致；`dlc_apply.py revert` 后 DLC01 与原版一致。

结论：**在满足 §1 版本校验与 §3 提供原版文件的前提下，本仓库可 clean clone 构建出可用补丁。**
