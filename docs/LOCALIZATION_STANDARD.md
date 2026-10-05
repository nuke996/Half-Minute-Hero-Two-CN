# Localization Engineering Standard

This document defines the default engineering standard for game localization projects.

It is intended to support long-term maintenance, reproducible builds, reverse-engineering preservation, and reuse by future localization efforts.

The current project may target one specific language, but the technical implementation should remain reusable for other locales whenever reasonably possible.

---

# 1. Project Goals

A localization project should aim to produce more than a one-time translated release.

The project should preserve:

- translation data
- terminology
- reverse-engineering findings
- extraction tools
- reinsertion tools
- archive tools
- font tools
- binary patches
- validation tools
- build instructions
- release procedures

A successful project should ideally allow future developers to reproduce the localization without rediscovering the same technical problems from scratch.

---

# 2. General Design Principles

## 2.1 Separate technology from language data

Generic localization infrastructure should remain independent from the current target language whenever technically possible.

Preferred separation:

```text
tools/
src/
locales/
```

Language-specific material should live under:

```text
locales/<locale>/
```

Examples:

```text
locales/zh-CN/
locales/zh-TW/
locales/ja-JP/
locales/ko-KR/
```

Do not assume one locale is the only possible target unless the game itself imposes that restriction.

## 2.2 Avoid unnecessary language-specific naming

Prefer generic names such as:

```text
build_font.py
extract_strings.py
import_strings.py
build_locale.py
patch_text_renderer.py
validate_translations.py
```

Avoid names such as:

```text
build_cn_font.py
patch_chinese_renderer.py
cn_strings.bin
```

unless the implementation is genuinely specific to that locale.

If a language-specific implementation is necessary, isolate it clearly from generic infrastructure.

## 2.3 Prefer reproducible automation

Whenever practical, replace manual procedures with scripts.

Preferred workflow:

```text
original game
    ↓
extract
    ↓
structured source data
    ↓
translation
    ↓
validation
    ↓
font generation
    ↓
resource rebuilding
    ↓
binary patching
    ↓
final package
```

Avoid workflows that depend on:

- manual hex editing
- undocumented GUI actions
- copied files from old work directories
- manually edited intermediate binary files
- files that exist only on one developer's machine

If a manual step cannot reasonably be automated, document it precisely.

---

# 3. Recommended Repository Structure

Use the following layout when appropriate:

```text
README.md
AGENTS.md
BUILDING.md
TRANSLATING.md
TECHNICAL.md
LICENSING.md

docs/
  LOCALIZATION_STANDARD.md
  PITFALLS.md
  FILE_FORMATS.md
  KNOWN_ISSUES.md

locales/
  <locale>/

src/
tools/
tests/
assets/

build/
dist/
```

Not every project needs every directory.

The exact structure may be adjusted when the game's technical requirements make another layout more appropriate.

Do not force meaningless abstraction for the sake of consistency.

---

# 4. Source Game Version Control

Every localization project should clearly identify the supported original game version.

Record when applicable:

- game title
- platform
- region
- distribution
- executable filename
- executable version
- file size
- SHA-256
- important archive hashes

Example:

```text
Platform:
Region:
Game version:
Executable:
File size:
SHA-256:
```

Binary patches must not silently modify unknown versions.

Patch tools should verify one or more of:

- file hash
- file size
- expected bytes
- version metadata

before modification.

---

# 5. Text Discovery

Before large-scale translation begins, determine where game text is stored.

Possible locations include:

- executable files
- DLLs
- ELF binaries
- scripts
- resource archives
- string tables
- subtitle files
- UI data
- save-related metadata
- hard-coded constants

Create a map of known text sources.

Example:

| Resource | Content | Encoding | Editable | Notes |
|---|---|---|---|---|
| UI.DAT | menu text | CP932 | yes | fixed slots |
| SCRIPT.BIN | dialogue | custom | yes | offset table |
| GAME.EXE | system text | ASCII | patch | hard-coded |

Do not assume all visible text comes from the same resource.

---

# 6. Text Encoding

Determine the actual runtime encoding before designing the translation pipeline.

Possible cases include:

- ASCII
- UTF-8
- UTF-16
- Shift-JIS / CP932
- GBK / CP936
- CP949
- custom multibyte encoding
- glyph-index encoding
- mixed encodings

Document:

- byte ranges
- multibyte rules
- null termination
- invalid byte behavior
- control-code interaction
- conversion behavior

Do not convert runtime resources to UTF-8 simply because UTF-8 is easier to edit.

Repository source data may use UTF-8 while build tools convert to the encoding required by the game.

---

# 7. Translation Data Format

Translation data should be structured and machine-readable.

Preferred formats include:

- TSV
- CSV
- JSON
- YAML
- PO
- custom structured text format with documented grammar

Whenever possible, preserve:

- stable ID
- source text
- target text
- speaker
- context
- resource origin
- technical notes
- length limits

Example:

```text
id	source	translation
1001	New Game	新游戏
1002	Load Game	读取游戏
```

or:

```json
{
  "id": 1001,
  "source": "New Game",
  "translation": "新游戏"
}
```

Do not store only translated strings if stable source mapping can be preserved.

---

# 8. Control Codes and Placeholders

Any systematic non-language token should be treated as protected until its behavior has been verified.

Examples:

```text
{0}
{1}
%s
%d
$n
\n
^xx
<tag>
<color>
\0
```

Validation should compare source and target placeholders.

It should detect:

- missing placeholders
- added placeholders
- reordered incompatible placeholders
- damaged control codes
- malformed tags

Do not translate unknown control codes.

Do not remove them merely because they look unusual.

---

# 9. Line Breaks and Wrapping

Determine whether the game uses:

- explicit line breaks
- automatic wrapping
- script-level wrapping
- fixed line lengths
- subtitle width limits
- UI-specific wrapping rules

Document the exact line-break representation.

Examples:

```text
\n
$n
0x0A
0x0D0A
custom command
```

Do not add manual line breaks unnecessarily.

If a game uses automatic wrapping, prefer preserving natural sentence structure unless layout requires otherwise.

---

# 10. String Length Limits

Determine whether each text resource is:

- dynamically sized
- offset-based
- null-terminated
- fixed-slot
- fixed-record
- fixed-byte-length
- fixed-character-count
- UI-width-limited
- executable-hard-coded

Document whether limits are measured in:

- bytes
- characters
- code units
- glyphs

Also determine whether lengths include:

- null terminators
- control codes
- headers
- alignment padding

Validation should reject dangerous overflows.

---

# 11. Font System Analysis

Before building a translated font, determine how the original game renders text.

Investigate:

- font texture format
- atlas format
- glyph order
- character mapping
- glyph size
- advance width
- kerning
- baseline
- line height
- missing-glyph behavior
- font fallback
- proportional vs fixed width
- UI scaling behavior

Do not assume replacing a font texture alone is sufficient.

Some games separate:

```text
glyph bitmap
character map
metrics
layout logic
```

All relevant components must be understood.

---

# 12. Font Generation

Whenever possible, font generation should be reproducible.

Preferred pipeline:

```text
translation data
    ↓
collect required characters
    ↓
font coverage check
    ↓
glyph rendering
    ↓
atlas generation
    ↓
character mapping
    ↓
metrics generation
    ↓
validation
```

The build should detect missing characters before producing a release.

Do not rely on manually edited font atlases if they can be generated.

---

# 13. Reverse Engineering Documentation

Important findings must be documented.

Useful information includes:

- file headers
- magic values
- field offsets
- pointer tables
- alignment rules
- string tables
- checksums
- hash tables
- archive indexes
- font structures
- executable offsets
- function behavior
- rendering paths
- linked resources

Whenever possible, record why a conclusion was reached.

Important findings should be classified as:

- Verified
- High-confidence deduction
- Unverified hypothesis

Do not write assumptions as facts.

---

# 14. Binary Patching

Binary patches must be defensive.

Before patching:

1. verify the target version
2. verify expected bytes
3. verify file size or hash where practical

During patching:

- write only intended bytes
- fail clearly on mismatch
- avoid silent fallback

After patching:

- verify modified bytes
- validate output
- preserve backup strategy where appropriate

Do not blindly patch fixed offsets in unknown versions.

---

# 15. Archive and Container Rebuilding

For each proprietary archive format, determine whether rebuilding requires more than replacing raw file contents.

Possible requirements include:

- TOC updates
- file size tables
- secondary manifests
- checksums
- CRC tables
- hashes
- alignment
- sector padding
- compression flags
- filename indexes
- entry ordering

Do not assume a generic archive packer produces a valid game archive.

Document game-specific archive behavior.

---

# 16. Linked and Mirrored Strings

Some logical strings may appear in multiple locations.

Examples:

```text
display name
inventory name
pickup message
document title
script identifier
```

or:

```text
Roxy
T.Roxy
```

Changing only one copy may cause:

- missing text
- incorrect references
- crashes
- broken script logic

Document linked groups.

Whenever possible, update them through one shared translation source.

---

# 17. Hard-Coded Strings

Maintain a list of known hard-coded text.

Possible locations:

- EXE
- ELF
- DLL
- scripts
- compiled UI data
- resource metadata

Hard-coded strings should not be assumed to participate in the normal translation import process.

Document them separately.

---

# 18. Validation

Every mature localization project should provide automated validation where possible.

Recommended checks include:

- untranslated entries
- empty translations
- duplicate IDs
- invalid encodings
- unsupported characters
- missing glyphs
- placeholder mismatches
- broken control codes
- fixed-slot overflow
- UI length warnings
- linked-string inconsistency
- malformed resource output
- unexpected file sizes
- invalid offsets
- unsupported original game versions

Validation failure should stop release generation when the issue can cause game breakage.

---

# 19. Multi-Language Reuse

When technically reasonable, the localization framework should support adding another locale without rewriting the entire project.

Preferred structure:

```text
locales/
  zh-CN/
  zh-TW/
  ja-JP/
  ko-KR/
```

Preferred build interface:

```text
build --locale <locale>
```

If another language requires new technical work, first determine whether the cause is:

1. an original engine limitation
2. an unnecessary limitation of the current framework

If the framework can be generalized at reasonable cost, prefer generalization.

---

# 20. Translation Workflow

Do not begin by translating the entire game.

Recommended order:

## Stage 1: Technical Reconnaissance

Confirm:

- supported game version
- text locations
- encoding
- font system
- archive format
- rendering behavior
- rebuild feasibility

## Stage 2: Minimal Proof of Concept

Translate only a small test set.

The test set should include where possible:

- ASCII
- target-language characters
- punctuation
- line breaks
- long strings
- UI strings
- dialogue
- multiple screens or contexts

Confirm that the game remains stable.

## Stage 3: Toolchain

Build:

- extraction
- import
- validation
- font generation
- patching
- archive rebuilding
- packaging

## Stage 4: Large-Scale Translation

Only begin full translation after the technical pipeline is stable.

## Stage 5: QA

Test:

- menus
- dialogue
- combat
- subtitles
- saves
- loading
- scene transitions
- UI scaling
- long play sessions

## Stage 6: Release

Produce a reproducible release package.

---

# 21. Build Reproducibility

A future developer should ideally be able to:

1. clone the repository
2. provide the required original game files
3. install documented dependencies
4. run the build command
5. reproduce the localization output

The project must not depend on:

- forgotten local files
- undocumented manual edits
- deleted intermediate binaries
- private directories
- chat-only instructions

If something is required to rebuild the project, it must be documented.

---

# 22. Repository Hygiene

Do not commit generated clutter.

Avoid permanent directories such as:

```text
final/
final2/
new/
new2/
old/
backup/
test/
temp/
```

Use defined output directories instead:

```text
build/
dist/
out/
```

Generated output should normally be excluded by `.gitignore`.

---

# 23. Copyrighted Game Files

Do not commit complete proprietary game files unless redistribution is explicitly permitted.

Examples include:

- game executables
- ELF files
- DLLs
- archives
- videos
- audio
- textures
- models
- proprietary fonts

Prefer distributing:

- scripts
- source code
- translation data
- patch files
- diffs
- build tools
- technical documentation

Users should normally provide their own original game files.

---

# 24. Licensing

Different parts of the repository may require different licenses.

Possible categories include:

- original project code
- translation text
- upstream source code
- third-party tools
- fonts
- game source text
- copyrighted game assets
- code governed by upstream EULAs

Do not assume one repository license automatically covers all content.

Document licensing boundaries in:

```text
LICENSING.md
```

---

# 25. Upstream Research and Attribution

If the project builds on prior work such as:

- fan translations
- undub projects
- reverse-engineering projects
- modernizer mods
- source ports
- extraction tools

then:

1. record the upstream project
2. record the author
3. record the relevant commit or release where possible
4. document what was reused
5. document what was independently verified
6. preserve upstream licensing requirements
7. avoid presenting upstream discoveries as original work

If the project is a fork, keep the history reasonably compatible with upstream when practical.

---

# 26. Technical History Preservation

Do not delete useful failed research simply because the final method is different.

Record meaningful failed approaches in:

```text
docs/PITFALLS.md
```

Examples:

- a font replacement that caused crashes
- an archive tool that produced invalid offsets
- an encoding method that corrupted saves
- an engine hook that worked only in menus
- a patch that broke another game version

Failed approaches can be valuable future documentation.

---

# 27. File Format Documentation

Custom formats should be documented in:

```text
docs/FILE_FORMATS.md
```

Where useful, include:

- structure diagrams
- offsets
- field meanings
- example values
- alignment
- encoding
- compression
- checksums
- unknown fields

Unknown fields should remain marked as unknown.

Do not invent explanations without evidence.

---

# 28. Known Issues

Player-visible limitations should be recorded in:

```text
docs/KNOWN_ISSUES.md
```

Examples:

- untranslated text
- clipping
- unsupported resolutions
- missing subtitles
- crashes in specific scenes
- unsupported game builds
- mod conflicts

Do not hide known limitations.

---

# 29. Documentation Maintenance

Documentation is part of the project, not an afterthought.

When code changes invalidate documentation, update both together.

Important project knowledge should not exist only in:

- chat history
- personal notes
- temporary files
- commit messages
- issue comments

Move durable knowledge into the repository.

---

# 30. Final Standard

A mature localization project should ideally allow:

- players to download and use a finished release
- developers to rebuild the localization from source
- translators to edit structured translation files
- researchers to understand the reverse-engineering work
- maintainers to reproduce technical decisions
- contributors to add another locale when feasible

The final goal is not merely a translated game.

The goal is a maintainable localization project whose technical knowledge survives beyond the original implementation.
