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
| 字体 | `WenQuanYi Bitmap Song 13px.ttf`（文泉驿点阵宋体，GPL-2.0，仓库自带于 `仓库/fonts/`） |
| 可选工具 | `zig` 工具链（仅在需要重建 `dinput8` 代理 DLL 时用到） |

字体：构建默认读取 `C:\Windows\Fonts\WenQuanYi Bitmap Song 13px.ttf`；
缺失时**不报错**，回退 GDI SimSun 16px 单色（无描边，观感下降）。
可用环境变量覆盖：`HMH2_FONT`（`wqy12/wqy13/wqy14/wqy16/simsun`）、`HMH2_THICK`、`HMH2_OUTLINE`。

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

> 建议：首次运行前，手工把上述 5 个主文件复制为 `*.bak`，DLC01 三个文件复制为
> `*.bak_dlc01_20260913`（脚本内部使用这两个固定后缀）。

---

# 4. 目录准备与路径配置

**[已验证] 仓库 `tools/` 内的脚本已按规范解除硬编码**：路径由 `tools/paths.py` 统一解析，
优先级为 **环境变量 > `config.local.json` > 仓库内相对默认值**。

配置方式（任选其一）：

1. 复制 `config.example.json` 为 `config.local.json`，填入 `game_dir`（游戏安装目录）：
   ```json
   { "game_dir": "D:\\Games\\Half Minute Hero Two", "locale": "zh-CN" }
   ```
2. 运行时指定：
   ```bash
   python tools/build.py --game-dir "D:\\Games\\Half Minute Hero Two" apply_menu
   # 或 set HMH2_GAME_DIR=D:\Games\Half Minute Hero Two
   ```

`game_dir` 需包含原版 `HMH2.exe`、`res/`、`DLC01/`。字体默认取 `assets/fonts/WenQuanYi Bitmap Song 13px.ttf`。

> 说明：作者原始工作目录 `_work/` 内的同名脚本**仍保留硬编码 BASE**（历史存档，本次未改动）。
> 仓库 `tools/` 才是对外可复现的规范版本；两者内容同源，`tools/` 为可重定位（relocatable）版。

---

# 5. 构建入口

## 5.1 统一脚本入口

```bash
python _work/runner.py <脚本名> [参数]
```
（在 `_work` 内运行，输出写入 `<脚本名>_run.txt`。）

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
| `apply_font` / `apply_nosync` / `apply_nocollide` / `apply_consistent` / `apply_nomech` | 历史测试包 A/B/C/E/D |
| `apply_noplace` / `apply_menu_safe` / `apply_menu_noml` | 变体（回退地名/保守 UI/退回单行） |

## 5.3 一键 `.bat`（由 `make_bats.py` 生成）

根目录当前存在的入口：

| bat | 调用 |
|---|---|
| `汉化-安装.bat` | `build_cn.py revert` -> `build_cn.py apply_menu` |
| `汉化-还原.bat` | `build_cn.py revert` |
| `汉化-导出校对.bat` | `export_review.py` |
| `汉化-导入校对.bat` | `import_review.py apply` |
| `汉化-导入校对-回滚.bat` | `import_review.py revert` |

另有大量历史/专项 bat（健康体检、说明文放行开关、Q16 键名保护开关、名字类回滚等），
见根目录与 `历史bat/`。

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

- 补丁产物直接**原地写入游戏目录**：`HMH2.exe`、`res/LANG_JA.s2a`、`res/LANG_EN.s2a`、
  `res/cscv.s2a`、`res/texture.s2a`（+ DLC01 三个文件）。
- **工具运行产物**（日志 `*.txt`、`collide_cache.json`、回滚/快照备份 `_pre_*/`、`_name_good/`、
  校对工作目录 `校对/`、`存档记录.md` 等）统一写入仓库 `build/`（定义见 `tools/paths.py`），
  与语言数据目录 `locales/zh-CN/` 严格分离。`build/` 已被 `.gitignore` 忽略。
- `dist/` 预留给"发布打包"（尚未实现）。
- 还原命令：`python tools/build.py revert`（从 `.bak` 覆盖回原文件）。

---

# 9. 可复现性现状（差距清单）

| 项 | 现状 | 结论 |
|---|---|---|
| exe 补丁 | 逐条校验原字节；离线与运行时两条路径等价 | **可复现** |
| 图集/字符表生成 | 从 `.bak` + 字体确定性生成 | **可复现**（依赖字体文件） |
| 文本导入 | 从 `text_v2.csv` + 守卫 JSON 确定性导入 | **基本可复现** |
| 游戏根路径 | 硬编码 `E:\SteamLibrary\...` | **不可复现**（需手工改） |
| 字形字体 | 依赖系统安装的 WenQuanYi；缺失静默降级 | **不可复现**（应改为仓库内相对路径 + 缺失即报错） |
| 构建输入 | 依赖 `_work/` 下大量 JSON 守卫、`.bak`、`collide_cache.json` 等本地状态 | **部分不可复现** |
| `collide_cache.json` | 缺失时现场重算（很慢） | 可重建但耗时 |
| 输出 | 原地写入，无独立构建目录 | 不符合规范 §22 |
| 母本校验 | `res/*.s2a` 无散列校验 | 应补充 |

**改进方向（尚未实施，属建议）：**
1. 用环境变量/配置文件（如 `config.local.json`）替代硬编码 `BASE`，并提供 `config.example.json`。
2. 字体改从仓库 `assets/fonts/` 相对路径读取；缺失**报错**而非静默降级。
3. 增加 `validate_inputs`：对原始 `HMH2.exe` / `res/*.s2a` 做散列校验。
4. 提供单一入口 `python build.py --locale zh-CN`，输出到 `build/`/`dist/`。
5. 明确哪些 `_work/*.json` 是"语言数据"（应入库）哪些是"构建产物/缓存"（应忽略）。

---

# 10. 校验与体检命令

```bash
python _work/build_cn.py check                # 各文件 原版/已修改 + 散列
python _work/t34_health.py                    # 项目体检，exit 0=全绿
python _work/t162_diff_audit.py <备份根> <批次id...>   # 零附带变化审计
python _work/t152_verify_g1.py                # 功能级反解（批次示例）
python _work/dlce_apply.py verify            # DLC01 三重验证（同 dlc_apply.py）
```

---

# 11. DLC01 独立流程

```bash
python _work/dlc_export.py            # 导出工作单（只读）
python _work/dlc_apply.py plan        # 生成写入计划
python _work/dlc_apply.py apply       # 写入（超容量即中止）
python _work/dlc_apply.py verify      # 三重验证（读回 / 无越界清零 / 记录尾一致）
python _work/dlc_apply.py revert      # 从 *.bak_dlc01_20260913 还原
```

**[已验证]** DLC01 写入只在自己原文占用范围内改写，绝不越界清零（v1 曾把记录尾清零导致剧情断链）。

---

# 12. 代理 DLL（运行时补丁）构建

```text
_work/proxydll/main.c            # 代理 DLL 源码
_work/proxydll/dinput8.def       # 导出表
_work/proxydll/gen_patch_bin.js  # 由 HMH2.exe.bak 生成 hm2zh_patch.bin（含自测）
_work/proxydll/build.bat         # 构建脚本（zig 工具链）
```

产物部署到游戏根目录：`dinput8.dll` + `hm2zh_patch.bin`。
`gen_patch_bin.js` 会把补丁虚拟应用到 `HMH2.exe.bak` 并与当前 `HMH2.exe` 的 `.text` 区逐字节比对作为自测。

---

# 13. 常见故障

| 症状 | 原因 | 处理 |
|---|---|---|
| `缺少 HMH2.exe.bak，无法打补丁` | 缺原版母本 | 提供原版 exe 并备份为 `.bak` |
| 找不到 `res/...` 文件 | `BASE` 路径不对 | 全局替换脚本内 `BASE` |
| 字模变细/无描边 | WenQuanYi 字体未安装 | 安装字体到 `C:\Windows\Fonts\` |
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
