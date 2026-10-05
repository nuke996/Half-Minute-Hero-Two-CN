# 勇者30：再次降临 — 简体中文汉化（Half Minute Hero Two CN）

面向 Steam PC 版《勇者30：再次降临》（Half Minute Hero Two）的简体中文汉化工程。

思路：**不动游戏机制**——把简体字模画进游戏字库图集、重写字符表与文本，实现"能玩、稳定、可回滚"的汉化。

> 版权须知：本仓库**不包含任何游戏本体文件**（`HMH2.exe`、`res/*.s2a`、DLC、音乐等）。
> 参与协作请自备 Steam 正版游戏。成品补丁请通过 Releases 单独分发，勿随附游戏文件。

---

# 项目

| 项 | 值 |
|---|---|
| 游戏 | Half Minute Hero Two（勇者30：再次降临） |
| 中文名 | 勇者30：再次降临 |
| 目标语言 | zh-CN（简体中文） |
| 平台 | Steam PC（Windows） |
| 支持版本 | 见下方"支持的游戏版本" |
| 状态 | 进行中，主线可玩；名字类分批中文化进行中 |

---

# 支持的游戏版本

```text
平台:      Steam PC / Windows (x86)
发行:      Steam
可执行:    HMH2.exe
文件大小:  1,985,536 字节
SHA-256:   1A313A50319BD5FE...（前 16）
MD5:       867308FCD87A（前 12）
```

完整母本散列见 `TECHNICAL.md` §1.1。未测试的版本不应声称为"支持"。

---

# 包含内容

- 主线剧情对话、菜单/UI、系统消息、说明文
- 称号 / 伙伴 / 职业 / 阵形 / 装备 / 技能 等名字类（分批进行）
- 章节标题、村落地名、小咕之歌歌词
- DLC01（时之女神宝物包）文本
- 字形图集与字符表扩容（覆盖率 100%，零缺字）

**刻意不包含 / 保留原文**（保护机制，见 `docs/KNOWN_ISSUES.md`）：
- 作为运行时查找"键"的名字串（约 27,044 处 / 5,042 种）
- 敌人名与敌人专用招式名（规划中）
- 含"勇者城"的少量台词
- ASCII 资源名/内部标识

---

# 安装

成品式（推荐，零依赖）：

1. 准备一份干净的支持版本游戏（Steam）。
2. 下载最新的汉化发布包。
3. 将发布包内文件覆盖到游戏目录（`HMH2.exe` 或 `dinput8.dll`+`hm2zh_patch.bin`、
   `res/LANG_JA.s2a`、`res/LANG_EN.s2a`、`res/cscv.s2a`、`res/texture.s2a`）。
4. 启动游戏。

或参照 `BUILDING.md` 进行构建。

> 当前装机采用 `dinput8.dll` 运行时补丁方案（磁盘 `HMH2.exe` 保持原版），
> 需一同分发 `dinput8.dll` 与 `hm2zh_patch.bin`。

# 卸载

- 成品式安装会在游戏目录中留下被覆盖/新增的文件；请事先备份原版文件，
  或用 Steam"验证游戏文件完整性"还原（会一并还原其他被改文件）。
- 脚本式安装可用 `汉化-还原.bat`（= `python _work/build_cn.py revert`）从 `.bak` 还原。

---

# 技术概览

```text
LANG 文本字节 --(CP932 解码)--> 字符 --(cscv 字符表: 字符->index)--> 图集格 --> 像素
```

- 为每个简体字分配**专属 CP932 载体码**，把点阵画进对应图集格，并重写字符表与文本。
- exe 需解开字符表 1280 上限（新增 `.atbl` 节 + 若干立即数，扩到 4096），
  当前通过 `dinput8.dll` 代理 DLL 在内存中完成。
- 详见 `TECHNICAL.md`。

---

# 仓库结构

现行结构（在游戏目录内）：

```text
汉化-*.bat                    一键脚本（安装/还原/校对/回滚）
_work/                        工具链与译表（build_cn.py、s2a.py、dlc_*.py、proxydll/ 等）
_work/outputs/text_v2.csv     主译表
_work/outputs/*.md            历史报告与术语表
仓库/                         既有整理版仓库（docs/ fonts/ bat 等）
```

规范建议结构（迁移目标）：

```text
locales/zh-CN/   翻译数据
tools/  src/     通用工具链
docs/            技术文档
assets/fonts/    字体
```

见 `AGENTS.md` 与 `docs/LOCALIZATION_STANDARD.md`。

---

# 从源码构建

需要：Windows、Python 3.13（64 位）、Pillow；字体（文泉驿点阵宋体 13px）随仓库提供于 `assets/fonts/`。

```bash
python -m pip install -r requirements.txt

# 方式一：把游戏目录写进 config.local.json（复制 config.example.json 后改 game_dir）
python tools/build.py plan        # 只统计，不改文件
python tools/build.py apply_menu  # 生产装机（自动含 DLC01 刷新 + Q16 键名保护）
python tools/build.py revert      # 还原

# 方式二：运行时指定游戏目录
python tools/build.py --game-dir "D:\\Games\\Half Minute Hero Two" apply_menu
```

路径解析见 `tools/paths.py`（环境变量 > `config.local.json` > 仓库相对路径）。详见 `BUILDING.md`。

---

# 翻译

- 主译表 `_work/outputs/text_v2.csv`，仅 `zh_new` 列可改。
- 控制符、编码、长度限制、校对流程见 `TRANSLATING.md`。
- 非程序员可用 `汉化-导出校对.bat` / `汉化-导入校对.bat` 进行校对。

---

# 已知问题

见 `docs/KNOWN_ISSUES.md`。要点：大量"未翻译"是刻意保留；对话误译（TODO-5）仍在推进；
敌人名未翻译；Steam 校验会还原汉化。

---

# 技术研究

见 `TECHNICAL.md`、`docs/FILE_FORMATS.md`、`docs/PITFALLS.md`。
这些文档同时保存成功发现与失败的尝试。

---

# 兼容性

- 与原版存档兼容（不修改存档）。
- 与 Steam 完整性校验冲突（会还原被改文件）。
- 游戏版本更新可能导致补丁失效（非支持版本）。
- 运行时方案使用 `dinput8.dll` 代理，勿与其他注入同一 DLL 的 Mod 混用。

---

# 开发状态

```text
文本提取:      完成
字形/字体:     完成（覆盖率 100%）
UI 翻译:       基本完成（少量标签保留原文）
对话翻译:      完成但质量待修订（TODO-5）
名字类翻译:    分批进行中
DLC01:         完成
回滚/审计体系: 完成
发布打包:      待规范（当前无 build/dist 目录）
```

---

# 贡献

可贡献：译文改进、术语审校、逆向研究、工具开发、兼容测试、bug 报告、文档。
贡献前请阅读 `TRANSLATING.md`、`TECHNICAL.md`、`LICENSING.md`。

# 问题反馈

报告问题时请提供：游戏版本、平台、汉化版本、locale、场景/关卡、截图、原文与期望、
复现步骤、日志、以及"不打汉化时是否也有此问题"。

---

# 许可

- 项目代码：MIT（`LICENSE`）
- 原创译文：CC BY-SA 4.0（`LICENSE-translations.md`）
- 字体：文泉驿点阵宋体，GPL-2.0（`仓库/fonts/GPL-2.0.txt`）
- 游戏原文与原始资源：版权归原权利人所有，不随仓库分发

详见 `LICENSING.md`。

# 版权声明

原游戏及其原文、商标、角色、媒体等资产归各自权利人所有。本项目为独立汉化。
除非明确允许，不包含任何完整游戏文件。

# 致谢

- 原游戏开发者与发行商
- 3DM（早期译文底本）
- 文泉驿点阵宋体作者
- 所有译者、校对者、测试者与贡献者

# 项目链接

```text
Repository: https://github.com/nuke996/Half-Minute-Hero-Two-CN
```
