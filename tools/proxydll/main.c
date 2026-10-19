// main.c — dinput8 代理 DLL（HMH2 汉化字形表补丁运行时版）
//
// 职责：
//   1) 转发系统 dinput8.dll 的 5 个导出（游戏只导入 DirectInput8Create）
//   2) 加载后启动补丁线程：读取同目录 hm2zh_patch.bin，把 build_cn.py patch_exe_unlock()
//      的等价补丁写入游戏内存（取代离线改 HMH2.exe）
//
// 设计要点：
//   - HMH2.exe 无 ASLR（DllCharacteristics=0x8100），但仍按 GetModuleHandle(NULL) 动态计算
//     基址差值，代码对未来重定位保持正确
//   - 先全量校验（只读），再 VirtualAlloc 数据区，最后 VirtualProtect(PAGE_EXECUTE_READWRITE)
//     写 .text —— 与项目记忆中的 DEP 保护规则一致；任何校验失败都不落一笔写入
//   - 数据区（坐标表+排序表 32KB）先尝试固定 0x5F4000（与离线补丁态一致便于对照），
//     失败则任意地址回退并回填立即数（type2 记录的 delta 相对 atbl 基址）
//   - 若检测到 exe 已是离线补丁态（T7），跳过打补丁并记录日志（游戏自洽运行）
//   - 全程写 hm2zh_patch.log 诊断日志：每次进程启动覆盖（不跨启动累积），行首含日期时间

#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <stdio.h>
#include <stdarg.h>
#include <string.h>

// ---------------------------------------------------------------- 日志
static char g_dir[MAX_PATH] = {0};

static void log_path(char* path) {
    lstrcpyA(path, g_dir);
    lstrcatA(path, "\\hm2zh_patch.log");
}

// 每次进程启动清空一次日志：旧实现全程用 "a" 追加，导致日志跨启动无限增长。
// 在 DllMain 里（任何 logln 之前）截断，此后本进程内仍以 "a" 追加。
static void log_truncate(void) {
    char path[MAX_PATH];
    log_path(path);
    FILE* f = fopen(path, "w");
    if (f) fclose(f);
}

static void logln(const char* fmt, ...) {
    char path[MAX_PATH];
    log_path(path);
    FILE* f = fopen(path, "a");
    if (!f) return;
    SYSTEMTIME st;
    GetLocalTime(&st);
    fprintf(f, "[%04u-%02u-%02u %02u:%02u:%02u.%03u] ",
            (unsigned)st.wYear, (unsigned)st.wMonth, (unsigned)st.wDay,
            (unsigned)st.wHour, (unsigned)st.wMinute, (unsigned)st.wSecond, (unsigned)st.wMilliseconds);
    va_list ap;
    va_start(ap, fmt);
    vfprintf(f, fmt, ap);
    va_end(ap);
    fputc('\n', f);
    fclose(f);
}

// ---------------------------------------------------------------- 系统 dinput8 转发
typedef HRESULT (__stdcall *PFN_DirectInput8Create)(HINSTANCE, DWORD, const void*, void**, void*);
typedef HRESULT (__stdcall *PFN_DllGetClassObject)(const void*, const void*, void**);
typedef HRESULT (__stdcall *PFN_HRESULT0)(void);

static PFN_DirectInput8Create g_pDirectInput8Create;
static PFN_DllGetClassObject  g_pDllGetClassObject;
static PFN_HRESULT0           g_pDllCanUnloadNow;
static PFN_HRESULT0           g_pDllRegisterServer;
static PFN_HRESULT0           g_pDllUnregisterServer;

// 导出名直接用真实函数名（__stdcall）。若编译产物导出带 @N 装饰，由 fix_exports.js 二进制修正。
__declspec(dllexport) HRESULT __stdcall DirectInput8Create(
        HINSTANCE hinst, DWORD dwVersion, const void* riidltf, void** ppvOut, void* punkOuter) {
    if (g_pDirectInput8Create)
        return g_pDirectInput8Create(hinst, dwVersion, riidltf, ppvOut, punkOuter);
    return E_FAIL;
}

__declspec(dllexport) HRESULT __stdcall DllGetClassObject(const void* rclsid, const void* riid, void** ppv) {
    if (g_pDllGetClassObject) return g_pDllGetClassObject(rclsid, riid, ppv);
    return E_FAIL;
}

__declspec(dllexport) HRESULT __stdcall DllCanUnloadNow(void) {
    if (g_pDllCanUnloadNow) return g_pDllCanUnloadNow();
    return S_FALSE;
}

__declspec(dllexport) HRESULT __stdcall DllRegisterServer(void) {
    if (g_pDllRegisterServer) return g_pDllRegisterServer();
    return E_FAIL;
}

__declspec(dllexport) HRESULT __stdcall DllUnregisterServer(void) {
    if (g_pDllUnregisterServer) return g_pDllUnregisterServer();
    return E_FAIL;
}

// ---------------------------------------------------------------- 补丁数据解析
// bin 格式（小端），由 _work/proxydll/gen_patch_bin.js 生成：
//   Header 16B: 'H2ZP' | u16 ver | u16 flags | u32 imagebase | u32 count
//   Type1 记录: u8 type=1 | u8 len | u8 window=0 | u8 rsv | u32 va | u32 expect=0 | u32 delta=0
//               | orig[len] | new[len]          —— 逐字节原值校验 + 写入
//   Type2 记录: u8 type=2 | u8 len=0 | u8 window | u8 rsv | u32 va | u32 expect | u32 delta
//               —— 在 va 起 window 字节内搜 u32 expect，替换为 atbl_base + delta

#pragma pack(push, 1)
typedef struct {
    unsigned char  type;
    unsigned char  len;
    unsigned char  window;
    unsigned char  rsv;
    unsigned int   va;
    unsigned int   expect;
    unsigned int   delta;
} RecHdr;
#pragma pack(pop)

static DWORD rd32(const unsigned char* p) {
    return (DWORD)p[0] | ((DWORD)p[1] << 8) | ((DWORD)p[2] << 16) | ((DWORD)p[3] << 24);
}

// ---------------------------------------------------------------- 补丁线程
static DWORD WINAPI PatchThread(LPVOID arg) {
    (void)arg;
    logln("=== hm2zh proxy dll ===");

    // ---- 读取补丁文件（可用环境变量 HM2ZH_PATCH 覆盖路径；默认为 DLL 同目录 hm2zh_patch.bin）----
    char path[MAX_PATH];
    char envPath[MAX_PATH];
    BOOL haveEnv = GetEnvironmentVariableA("HM2ZH_PATCH", envPath, MAX_PATH)
                   && envPath[0] && GetFileAttributesA(envPath) != INVALID_FILE_ATTRIBUTES;
    if (haveEnv) {
        lstrcpyA(path, envPath);
        logln("使用环境变量 HM2ZH_PATCH 指定的补丁文件: %s", path);
    } else {
        lstrcpyA(path, g_dir);
        lstrcatA(path, "\\hm2zh_patch.bin");
    }
    FILE* f = fopen(path, "rb");
    if (!f) {
        logln("FAIL: 补丁文件不存在: %s", path);
        return 1;
    }
    fseek(f, 0, SEEK_END);
    long fsize = ftell(f);
    fseek(f, 0, SEEK_SET);
    if (fsize < 16 || fsize > 1024 * 1024) {
        logln("FAIL: 补丁文件尺寸异常 (%ld)", fsize);
        fclose(f);
        return 1;
    }
    static unsigned char bin[1024 * 1024];
    if (fread(bin, 1, (size_t)fsize, f) != (size_t)fsize) {
        logln("FAIL: 补丁文件读取失败");
        fclose(f);
        return 1;
    }
    fclose(f);

    if (memcmp(bin, "H2ZP", 4) != 0) {
        logln("FAIL: 补丁文件魔数不符");
        return 1;
    }
    unsigned ver = bin[4] | (bin[5] << 8);
    unsigned count = rd32(bin + 12);
    if (ver != 1 || count == 0 || count > 4096) {
        logln("FAIL: 补丁文件版本/记录数异常 (ver=%u count=%u)", ver, count);
        return 1;
    }
    logln("补丁文件: %ld 字节, %u 条记录", fsize, count);

    // ---- 解析记录 ----
    static RecHdr recs[4096];
    static const unsigned char* rdata[4096]; // type1: orig+len, new+len 连续存放
    long off = 16;
    unsigned nType1 = 0, nType2 = 0;
    DWORD minVa = 0xFFFFFFFF, maxVa = 0;
    for (unsigned i = 0; i < count; i++) {
        if (off + 16 > fsize) { logln("FAIL: 记录 %u 越界", i); return 1; }
        RecHdr r;
        memcpy(&r, bin + off, 16);
        off += 16;
        if (r.type == 1) {
            if (r.len == 0 || r.len > 32 || off + (long)r.len * 2 > fsize) {
                logln("FAIL: type1 记录 %u 长度异常 (%u)", i, r.len);
                return 1;
            }
            rdata[i] = bin + off;
            off += (long)r.len * 2;
            nType1++;
        } else if (r.type == 2) {
            if (r.window < 4 || r.window > 64) {
                logln("FAIL: type2 记录 %u 窗口异常 (%u)", i, r.window);
                return 1;
            }
            rdata[i] = NULL;
            nType2++;
        } else {
            logln("FAIL: 未知记录类型 %u (记录 %u)", r.type, i);
            return 1;
        }
        recs[i] = r;
        if (r.va < minVa) minVa = r.va;
        DWORD end = r.va + (r.type == 1 ? r.len : r.window);
        if (end > maxVa) maxVa = end;
    }
    if (off != fsize) logln("WARN: 补丁文件尾部有 %ld 字节未消费", fsize - off);
    logln("记录统计: type1=%u type2=%u 作用域 VA 0x%08X..0x%08X", nType1, nType2, minVa, maxVa);

    // ---- exe 基址 ----
    HMODULE exe = GetModuleHandleA(NULL);
    DWORD base = (DWORD)(uintptr_t)exe;
    DWORD delta = base - rd32(bin + 8); // imagebase 期望值 0x400000
    logln("exe 基址=0x%08X (与期望基址差值=0x%X)", base, delta);

    // ---- 第一遍：只读全量校验 ----
    enum { S_ORIG = 0, S_ALREADY = 1, S_BAD = 2 };
    int allState = -1; // 0=全原版 1=全已补 2=有坏
    unsigned badRec = 0xFFFFFFFF;
    for (unsigned i = 0; i < count; i++) {
        const RecHdr* r = &recs[i];
        const unsigned char* mem = (const unsigned char*)(uintptr_t)(base + (r->va - rd32(bin + 8)));
        int st;
        if (r->type == 1) {
            if (memcmp(mem, rdata[i], r->len) == 0) {
                st = S_ORIG;
            } else if (memcmp(mem, rdata[i] + r->len, r->len) == 0) {
                st = S_ALREADY;
            } else {
                st = S_BAD;
                if (badRec == 0xFFFFFFFF) {
                    badRec = i;
                    char o[128], c[128], n[128];
                    for (unsigned k = 0; k < r->len && k < 16; k++) {
                        sprintf(o + k * 2, "%02X", rdata[i][k]);
                        sprintf(c + k * 2, "%02X", mem[k]);
                        sprintf(n + k * 2, "%02X", rdata[i][r->len + k]);
                    }
                    logln("校验失败@记录%u VA=0x%08X 期望=%s 现况=%s 新值=%s",
                          i, r->va, o, c, n);
                }
            }
        } else {
            // type2: 窗口内搜 expect
            unsigned found = 0;
            for (unsigned k = 0; k + 4 <= r->window; k++) {
                if (rd32(mem + k) == r->expect) { found = 1; break; }
            }
            st = found ? S_ORIG : S_BAD;
            if (st == S_BAD && badRec == 0xFFFFFFFF) {
                badRec = i;
                logln("校验失败@记录%u VA=0x%08X 窗口内未找到 expect=0x%08X", i, r->va, r->expect);
            }
        }
        // 状态一致性聚合
        if (allState == -1) allState = (st == S_BAD) ? 2 : st;
        else if (st != allState) allState = 2;
        if (allState == 2 && badRec != 0xFFFFFFFF && i == count - 1) break;
    }

    if (allState == 2) {
        logln("ABORT: 校验不一致（坏记录=%u），未写入任何字节，游戏按当前状态运行", badRec);
        return 1;
    }
    if (allState == 1) {
        logln("SKIP: exe 已是补丁态（离线补丁未还原？），无需运行时补丁");
        return 0;
    }

    // ---- 分配数据区（坐标表 16KB + 排序表 16KB）----
    // 注意：VirtualAlloc 的 lpAddress 按 64KB 粒度向下取整。0x5F4000 非 64KB 对齐，
    // 直接请求会被系统落到 0x5F0000。因此先预留对齐块 [0x5F0000,0x600000)，
    // 再在其内提交 [0x5F4000,0x5FC000)——与 T7 离线补丁的 .atbl 节完全同址。
    LPVOID atbl = VirtualAlloc((LPVOID)0x005F0000, 0x10000, MEM_RESERVE, PAGE_NOACCESS);
    int fixed = 0;
    if (atbl == (LPVOID)0x005F0000) {
        LPVOID c = VirtualAlloc((LPVOID)0x005F4000, 0x8000, MEM_COMMIT, PAGE_READWRITE);
        if (c == (LPVOID)0x005F4000) {
            atbl = c;   // 基址必须取 commit 返回值 0x5F4000，而非预留块首 0x5F0000
            fixed = 1;
        } else {
            VirtualFree(atbl, 0, MEM_RELEASE);
            atbl = NULL;
        }
    } else if (atbl) {
        VirtualFree(atbl, 0, MEM_RELEASE);
        atbl = NULL;
    }
    if (!atbl) {
        atbl = VirtualAlloc(NULL, 0x8000, MEM_RESERVE | MEM_COMMIT, PAGE_READWRITE);
    }
    if (!atbl) {
        logln("ABORT: atbl 数据区分配失败 (GetLastError=%u)，未写入任何字节", (unsigned)GetLastError());
        return 1;
    }
    DWORD atblBase = (DWORD)(uintptr_t)atbl;
    logln("atbl 数据区: 0x%08X (%s, 32KB, PAGE_READWRITE)", atblBase, fixed ? "固定 0x5F4000" : "回退地址");

    // ---- 第二遍：写入 ----
    DWORD oldProt = 0;
    // minVa/maxVa 是期望基址下的 VA；映射到当前基址
    DWORD spanLo = base + (minVa - rd32(bin + 8));
    DWORD spanHi = base + (maxVa - rd32(bin + 8));
    if (!VirtualProtect((LPVOID)(uintptr_t)spanLo, spanHi - spanLo, PAGE_EXECUTE_READWRITE, &oldProt)) {
        logln("ABORT: VirtualProtect 失败 (GetLastError=%u)", (unsigned)GetLastError());
        return 1;
    }
    for (unsigned i = 0; i < count; i++) {
        const RecHdr* r = &recs[i];
        unsigned char* mem = (unsigned char*)(uintptr_t)(base + (r->va - rd32(bin + 8)));
        if (r->type == 1) {
            memcpy(mem, rdata[i] + r->len, r->len);
        } else {
            unsigned found = 0xFFFFFFFF;
            for (unsigned k = 0; k + 4 <= r->window; k++) {
                if (rd32(mem + k) == r->expect) { found = k; break; }
            }
            if (found == 0xFFFFFFFF) {
                // 理论不可达（第一遍已验过），保险处理
                logln("FAIL: 写入阶段记录 %u 未找到 expect（异常！）", i);
                VirtualProtect((LPVOID)(uintptr_t)spanLo, spanHi - spanLo, oldProt, &oldProt);
                return 1;
            }
            DWORD val = atblBase + r->delta;
            mem[found + 0] = (unsigned char)(val & 0xFF);
            mem[found + 1] = (unsigned char)((val >> 8) & 0xFF);
            mem[found + 2] = (unsigned char)((val >> 16) & 0xFF);
            mem[found + 3] = (unsigned char)((val >> 24) & 0xFF);
        }
    }
    VirtualProtect((LPVOID)(uintptr_t)spanLo, spanHi - spanLo, oldProt, &oldProt);
    logln("PATCH OK: %u 条记录全部写入, atbl=0x%08X", count, atblBase);
    return 0;
}

// ================================================================ 诊断插桩
// 目的：定位游戏"按名字查找"机制对字符串的比较点，为后续让机制名上屏中文提供落点。
// 激活条件（任一）：
//   - DLL 同目录存在标记文件 hm2zh_diag.on
//   - 环境变量 HM2ZH_DIAG 非空
// 日志：<DLL目录>\hm2zh_diag.log（每次启动覆盖）
//
// 插桩 1：strncmp@exe 0x54CC00（CRT 静态链接里唯一的"按字节比较 n 长度"原语）
//   入口 6 字节 = 53 56 8B 4C 24 0C (push ebx; push esi; mov ecx,[esp+0xC])
//   以 E9 rel32 + 90 覆盖，跳入自建 stub；stub 保存寄存器→调用 LogStrncmp→
//   重放被覆盖的 6 字节→跳回 0x54CC06。
// 插桩 2：exe 导入表里的 CreateFileW/A —— 只记录路径含 s2a/lang/cscv 的打开动作。

static volatile LONG g_diag = 0;
static FILE* g_diagf = NULL;
static LONG g_diaglock = 0;
static unsigned g_diaglines = 0;
#define DIAG_MAX_LINES 400000u

static void diag_lock(void) {
    while (InterlockedExchange(&g_diaglock, 1)) Sleep(0);
}
static void diag_unlock(void) {
    InterlockedExchange(&g_diaglock, 0);
}

static void diagln(const char* fmt, ...) {
    if (!g_diag || !g_diagf) return;
    diag_lock();
    if (g_diaglines >= DIAG_MAX_LINES) {
        if (g_diaglines == DIAG_MAX_LINES) {
            fprintf(g_diagf, "[limit] 已达 %u 行上限，后续不再记录\n", DIAG_MAX_LINES);
            fflush(g_diagf);
            g_diaglines++;
        }
        diag_unlock();
        return;
    }
    SYSTEMTIME st;
    GetLocalTime(&st);
    fprintf(g_diagf, "[%04u-%02u-%02u %02u:%02u:%02u.%03u] ",
            (unsigned)st.wYear, (unsigned)st.wMonth, (unsigned)st.wDay,
            (unsigned)st.wHour, (unsigned)st.wMinute, (unsigned)st.wSecond, (unsigned)st.wMilliseconds);
    va_list ap;
    va_start(ap, fmt);
    vfprintf(g_diagf, fmt, ap);
    va_end(ap);
    fputc('\n', g_diagf);
    fflush(g_diagf);
    g_diaglines++;
    diag_unlock();
}

// 可打印化：非 ASCII 可打印字节输出为 \xHH，避免日志编码混乱
static void diag_esc(char* out, size_t outsz, const char* s, unsigned maxn) {
    size_t k = 0;
    if (!s) { out[0] = 0; return; }
    for (unsigned i = 0; i < maxn && s[i]; i++) {
        unsigned char c = (unsigned char)s[i];
        if (c == '\\' || c == '"') {
            if (k + 2 >= outsz) break;
            out[k++] = '\\'; out[k++] = (char)c;
        } else if (c >= 0x20 && c < 0x7F) {
            if (k + 1 >= outsz) break;
            out[k++] = (char)c;
        } else {
            if (k + 4 >= outsz) break;
            sprintf(out + k, "\\x%02X", c);
            k += 4;
        }
    }
    out[k] = 0;
}

// ---- 去重表 + 每调用点预算：只记录首次出现的 (tag,caller,n,s1,s2)，并对每个调用点限流 ----
#define DEDUP_SLOTS 32768u
static unsigned g_dedup[DEDUP_SLOTS];

// 一轮实测确认的"路径/扩展名解析"调用点（会以子串滑动方式刷屏），直接排除
static const DWORD g_caller_deny[] = {
    0x0046A21A, 0x00492BF3, 0x00492C0B, 0x00497120, 0x00497138
};

typedef struct { DWORD caller; unsigned count; } CallerSlot;
#define CALLER_SLOTS 64u
#define PER_CALLER_MAX 48u
static CallerSlot g_callers[CALLER_SLOTS];

// 该调用点是否允许继续记录（未被排除且未超预算）
static int caller_allow(DWORD caller) {
    if (caller == 0) caller = 1;   // 0 用作"空槽"标记
    for (unsigned i = 0; i < sizeof(g_caller_deny) / sizeof(g_caller_deny[0]); i++)
        if (g_caller_deny[i] == caller) return 0;
    for (unsigned i = 0; i < CALLER_SLOTS; i++) {
        if (g_callers[i].caller == caller) {
            if (g_callers[i].count >= PER_CALLER_MAX) return 0;
            g_callers[i].count++;
            return 1;
        }
    }
    for (unsigned i = 0; i < CALLER_SLOTS; i++) {
        if (g_callers[i].caller == 0) { g_callers[i].caller = caller; g_callers[i].count = 1; return 1; }
    }
    return 0;   // 调用点表已满：放弃记录
}

static unsigned diag_hash3(char tag, DWORD caller, const char* s1, const char* s2, unsigned n) {
    unsigned h = caller * 2654435761u ^ (n + 0x9E3779B9u) ^ ((unsigned)(unsigned char)tag << 24);
    const unsigned char* p;
    for (p = (const unsigned char*)s1; *p; p++) h = (h * 16777619u) ^ *p;
    h ^= 0x85EBCA6Bu;
    for (p = (const unsigned char*)s2; *p; p++) h = (h * 16777619u) ^ *p;
    return h | 1u;
}

static int diag_dedup_insert(unsigned h) {
    for (unsigned i = 0; i < 8; i++) {
        unsigned idx = (h * 2654435761u + i * 40503u) & (DEDUP_SLOTS - 1);
        unsigned cur = g_dedup[idx];
        if (cur == 0) { g_dedup[idx] = h; return 1; }
        if (cur == h) return 0;
    }
    return 0;
}

// 文本性判据：允许 ASCII 可打印，也允许 CP932/高位字节（日文/载体码），
// 以免漏掉"日文键名 vs 日文键名"这类比较（上一轮正是被这条规则漏掉的）。
static int looks_text(const char* s) {
    unsigned char c = (unsigned char)s[0];
    return (c >= 0x20 && c < 0x7F) || (c >= 0x81 && c <= 0x9F) || c >= 0xE0;
}

// 通用过滤：通过则允许写一行日志
static int rec_begin(char tag, DWORD caller, const char* s1, const char* s2, unsigned n) {
    if (!g_diag || !g_diagf) return 0;
    if (!s1 || !s2) return 0;
    if ((uintptr_t)s1 < 0x1000 || (uintptr_t)s2 < 0x1000) return 0;
    if (!looks_text(s1) && !looks_text(s2)) return 0;
    if (!caller_allow(caller)) return 0;
    return diag_dedup_insert(diag_hash3(tag, caller, s1, s2, n));
}

// 3 参比较（strncmp 族）的落地函数（__cdecl；由 stub 以 cdecl 调用）
__attribute__((noinline))
void LogCmp3(DWORD caller, const char* s1, const char* s2, DWORD n) {
    if (n == 0 || (n != 0xFFFFFFFFu && n > 4096)) return;   // n=0 无意义；超大 n 视为批量
    if (!rec_begin('N', caller, s1, s2, n)) return;
    char e1[96], e2[96];
    diag_esc(e1, sizeof(e1), s1, 48);
    diag_esc(e2, sizeof(e2), s2, 48);
    diagln("N caller=0x%08X n=%u s1=\"%s\" s2=\"%s\"", (unsigned)caller, (unsigned)n, e1, e2);
}

// 2 参比较（strcmp / strstr 族）的落地函数
__attribute__((noinline))
void LogCmp2(DWORD caller, const char* s1, const char* s2) {
    if (!rec_begin('C', caller, s1, s2, 0xFFFFFFFFu)) return;
    char e1[96], e2[96];
    diag_esc(e1, sizeof(e1), s1, 48);
    diag_esc(e2, sizeof(e2), s2, 48);
    diagln("C caller=0x%08X s1=\"%s\" s2=\"%s\"", (unsigned)caller, e1, e2);
}

// strstr（子串搜索）的落地函数
__attribute__((noinline))
void LogStrstr(DWORD caller, const char* s1, const char* s2) {
    if (!rec_begin('S', caller, s1, s2, 0xFFFFFFFFu)) return;
    char e1[96], e2[96];
    diag_esc(e1, sizeof(e1), s1, 48);
    diag_esc(e2, sizeof(e2), s2, 48);
    diagln("S caller=0x%08X s1=\"%s\" s2=\"%s\"", (unsigned)caller, e1, e2);
}

// 名字哈希输入（0x46C070 / 0x46C0C0）的落地函数：只记录很可能是"物品/技能/职业名"的短字符串。
// 过滤：非空指针且 >=0x1000；长度 1..48；逐字节 >=0x20（无控制字节）；不含 '/' 与 '\'（排除路径）。
__attribute__((noinline))
void LogNameHash(DWORD caller, const char* s) {
    if (!g_diag || !g_diagf) return;
    if (!s || (uintptr_t)s < 0x1000) return;
    unsigned n = 0;
    while (n < 48 && s[n]) {
        unsigned char c = (unsigned char)s[n];
        if (c < 0x20 || c == '/' || c == '\\') return;   // 控制字节或路径：丢弃
        n++;
    }
    if (n == 0) return;                                  // 空串：丢弃
    if (!caller_allow(caller)) return;
    if (!diag_dedup_insert(diag_hash3('H', caller, s, "", n))) return;
    char e[128];
    diag_esc(e, sizeof(e), s, 48);
    diagln("H caller=0x%08X s=\"%s\"", (unsigned)caller, e);
}


// ---- 通用内联钩子 ----
// 覆盖目标函数入口前 6 字节为 E9 rel32 + 90，跳入自建 stub；stub 动作：
//   pushad → 依次压入 [参数...][返回地址] → call 落地函数 → add esp → popad →
//   重放入口被覆盖的完整指令（>=6 字节，须落在指令边界） → jmp 回 va+replayLen
//
// 各次 push 用同一位移 disp = 0x20 + 4*nargs：pushad 后返回地址位于 [esp+0x20]，
// 第 k 个参数位于 [esp+0x20+4k]；每 push 一次 esp 减 4、目标相对位移也加 4，两者相抵，
// 故以同一个立即数即可实现"参数逆序压栈 + 返回地址最后压入"。
#define MAX_HOOKS 8
static unsigned char* g_hook_p[MAX_HOOKS];
static unsigned char g_hook_orig[MAX_HOOKS][8];
static unsigned g_hook_np = 0;

static int install_cmp_hook(DWORD exeBase, DWORD imageBase, DWORD va, DWORD resumeVa,
                            const unsigned char* expect, unsigned replayLen,
                            void* landing, unsigned nargs, const char* tag) {
    unsigned char* p = (unsigned char*)(uintptr_t)(exeBase + (va - imageBase));
    MEMORY_BASIC_INFORMATION mbi;
    if (!VirtualQuery(p, &mbi, sizeof(mbi)) || mbi.State != MEM_COMMIT ||
        (mbi.Protect & (PAGE_NOACCESS | PAGE_GUARD))) {
        diagln("HOOK FAIL(%s): 目标页不可读 VA=0x%08X", tag, (unsigned)(uintptr_t)p);
        return 0;
    }
    if (replayLen < 6 || replayLen > 8) { diagln("HOOK FAIL(%s): replayLen 非法", tag); return 0; }
    if (memcmp(p, expect, replayLen) != 0) {
        char now[40];
        unsigned k;
        for (k = 0; k < replayLen && k < 16; k++) sprintf(now + k * 2, "%02X", p[k]);
        diagln("HOOK FAIL(%s): 原字节不符 VA=0x%08X now=%s", tag, (unsigned)(uintptr_t)p, now);
        return 0;
    }
    if (g_hook_np >= MAX_HOOKS) { diagln("HOOK FAIL(%s): 钩子表已满", tag); return 0; }
    unsigned char* stub = (unsigned char*)VirtualAlloc(NULL, 128, MEM_COMMIT | MEM_RESERVE, PAGE_EXECUTE_READWRITE);
    if (!stub) { diagln("HOOK FAIL(%s): stub 分配失败", tag); return 0; }

    unsigned n = 0, i, k;
    stub[n++] = 0x60;                                     // pushad
    unsigned disp = 0x20 + 4 * nargs;
    for (i = 0; i <= nargs; i++) {                        // 压入 参数(nargs..1) 与 返回地址
        stub[n++] = 0xFF; stub[n++] = 0x74; stub[n++] = 0x24; stub[n++] = (unsigned char)disp;
    }
    unsigned e8 = n;                                      // call landing
    stub[n++] = 0xE8; for (k = 0; k < 4; k++) stub[n++] = 0;
    stub[n++] = 0x83; stub[n++] = 0xC4; stub[n++] = (unsigned char)(4 * (nargs + 1));  // add esp,..
    stub[n++] = 0x61;                                     // popad
    memcpy(stub + n, expect, replayLen); n += replayLen;  // 重放入口指令
    unsigned e9 = n;                                      // jmp resume
    stub[n++] = 0xE9; for (k = 0; k < 4; k++) stub[n++] = 0;

    DWORD sb = (DWORD)(uintptr_t)stub;
    DWORD rel1 = (DWORD)(uintptr_t)landing - (sb + e8 + 5);
    DWORD rel2 = (exeBase + (resumeVa - imageBase)) - (sb + e9 + 5);
    memcpy(stub + e8 + 1, &rel1, 4);
    memcpy(stub + e9 + 1, &rel2, 4);
    FlushInstructionCache(GetCurrentProcess(), stub, n);

    DWORD old = 0;
    if (!VirtualProtect(p, 6, PAGE_EXECUTE_READWRITE, &old)) {
        diagln("HOOK FAIL(%s): VirtualProtect 失败 (%u)", tag, (unsigned)GetLastError());
        VirtualFree(stub, 0, MEM_RELEASE);
        return 0;
    }
    DWORD rel3 = sb - (DWORD)(uintptr_t)(p + 5);
    unsigned char code[6] = {0xE9,
                             (unsigned char)(rel3 & 0xFF), (unsigned char)((rel3 >> 8) & 0xFF),
                             (unsigned char)((rel3 >> 16) & 0xFF), (unsigned char)((rel3 >> 24) & 0xFF),
                             0x90};
    memcpy(p, code, 6);
    VirtualProtect(p, 6, old, &old);
    FlushInstructionCache(GetCurrentProcess(), p, 6);
    g_hook_p[g_hook_np] = p;
    memcpy(g_hook_orig[g_hook_np], expect, 6);
    g_hook_np++;
    diagln("HOOK OK(%s): 0x%08X -> stub 0x%08X", tag, (unsigned)(uintptr_t)p, sb);
    return 1;
}

// ---- 名字哈希函数专用钩子（0x46C070 / 0x46C0C0）----
// 这两个入口与 strncmp/strcmp 族形态不同，install_cmp_hook 无法复用：
//   (1) 参数经 ECX 传入（入口第一条指令是 mov esi, ecx，MSVC __fastcall/__thiscall），
//       通用 stub 的"按栈槽取参"模型拿不到字符串指针；
//   (2) 入口前 7 字节含短跳分支（test esi,esi; jne 0x46C07B），原样重放的 rel8 在
//       换址后不会指向原目标。
// 因此本安装器自建 stub：
//   pushad;
//   mov edx,[esp+0x18]  (pushad 后 [esp+0x18] = 原 ECX = 字符串 s)
//   push edx            (第 2 个实参 s)
//   push [esp+0x24]     (pushad+1 次 push 后 [esp+0x24] = 原返回地址 = caller)
//   call LogNameHash; add esp,8; popad;
//   原样重放入口 7 字节: 56 8B F1 85 F6 75 04
//   空指针路径(esi==0)就地内联: 33 C0 5E C3 (xor eax,eax; pop esi; ret)
//   E9 rel32 -> resumeVa (分支目标: 非空路径 0x46C07B / 0x46C0CB)
// 关键：入口 jne 的 rel8=+4 使其在 stub 内的落点恰为末尾 E9 的首字节，故分支语义重定位后仍正确。
static int install_hash_hook(DWORD exeBase, DWORD imageBase, DWORD va, DWORD resumeVa,
                             const unsigned char* expect7, void* landing, const char* tag) {
    unsigned char* p = (unsigned char*)(uintptr_t)(exeBase + (va - imageBase));
    MEMORY_BASIC_INFORMATION mbi;
    if (!VirtualQuery(p, &mbi, sizeof(mbi)) || mbi.State != MEM_COMMIT ||
        (mbi.Protect & (PAGE_NOACCESS | PAGE_GUARD))) {
        diagln("HOOK FAIL(%s): 目标页不可读 VA=0x%08X", tag, (unsigned)va);
        return 0;
    }
    if (memcmp(p, expect7, 7) != 0) {
        char now[40];
        unsigned k;
        for (k = 0; k < 7; k++) sprintf(now + k * 2, "%02X", p[k]);
        now[14] = 0;
        diagln("HOOK FAIL(%s): 原字节不符 VA=0x%08X now=%s", tag, (unsigned)va, now);
        return 0;
    }
    if (g_hook_np >= MAX_HOOKS) { diagln("HOOK FAIL(%s): 钩子表已满", tag); return 0; }
    unsigned char* stub = (unsigned char*)VirtualAlloc(NULL, 128, MEM_COMMIT | MEM_RESERVE, PAGE_EXECUTE_READWRITE);
    if (!stub) { diagln("HOOK FAIL(%s): stub 分配失败", tag); return 0; }

    unsigned n = 0, k;
    stub[n++] = 0x60;                                                            // pushad
    stub[n++] = 0x8B; stub[n++] = 0x54; stub[n++] = 0x24; stub[n++] = 0x18;      // mov edx,[esp+0x18] (=原 ECX)
    stub[n++] = 0x52;                                                            // push edx
    stub[n++] = 0xFF; stub[n++] = 0x74; stub[n++] = 0x24; stub[n++] = 0x24;      // push dword [esp+0x24] (=原返回地址)
    unsigned e8 = n;                                                             // call LogNameHash
    stub[n++] = 0xE8; for (k = 0; k < 4; k++) stub[n++] = 0;
    stub[n++] = 0x83; stub[n++] = 0xC4; stub[n++] = 0x08;                        // add esp,8
    stub[n++] = 0x61;                                                            // popad
    memcpy(stub + n, expect7, 7); n += 7;                                        // 重放入口 7 字节（含 jne）
    stub[n++] = 0x33; stub[n++] = 0xC0;                                          // xor eax,eax (esi==0 路径)
    stub[n++] = 0x5E; stub[n++] = 0xC3;                                          // pop esi; ret
    unsigned e9 = n;                                                             // jmp resumeVa
    stub[n++] = 0xE9; for (k = 0; k < 4; k++) stub[n++] = 0;

    DWORD sb = (DWORD)(uintptr_t)stub;
    DWORD rel1 = (DWORD)(uintptr_t)landing - (sb + e8 + 5);
    DWORD rel2 = (exeBase + (resumeVa - imageBase)) - (sb + e9 + 5);
    memcpy(stub + e8 + 1, &rel1, 4);
    memcpy(stub + e9 + 1, &rel2, 4);
    FlushInstructionCache(GetCurrentProcess(), stub, n);

    DWORD old = 0;
    if (!VirtualProtect(p, 6, PAGE_EXECUTE_READWRITE, &old)) {
        diagln("HOOK FAIL(%s): VirtualProtect 失败 (%u)", tag, (unsigned)GetLastError());
        VirtualFree(stub, 0, MEM_RELEASE);
        return 0;
    }
    DWORD rel3 = sb - (DWORD)(uintptr_t)(p + 5);
    unsigned char code[6] = {0xE9,
                             (unsigned char)(rel3 & 0xFF), (unsigned char)((rel3 >> 8) & 0xFF),
                             (unsigned char)((rel3 >> 16) & 0xFF), (unsigned char)((rel3 >> 24) & 0xFF),
                             0x90};
    memcpy(p, code, 6);
    VirtualProtect(p, 6, old, &old);
    FlushInstructionCache(GetCurrentProcess(), p, 6);
    g_hook_p[g_hook_np] = p;
    memcpy(g_hook_orig[g_hook_np], expect7, 6);
    g_hook_np++;
    diagln("HOOK OK(%s): 0x%08X -> stub 0x%08X resume=0x%08X", tag, (unsigned)(uintptr_t)p, sb, (unsigned)resumeVa);
    return 1;
}

// 卸载时还原全部被覆盖的入口字节，避免 DLL 卸载后 exe 跳入已释放的 stub
static void unhook_all(void) {
    for (unsigned i = 0; i < g_hook_np; i++) {
        unsigned char* p = g_hook_p[i];
        if (p) {
            DWORD old = 0;
            if (VirtualProtect(p, 6, PAGE_EXECUTE_READWRITE, &old)) {
                memcpy(p, g_hook_orig[i], 6);
                VirtualProtect(p, 6, old, &old);
                FlushInstructionCache(GetCurrentProcess(), p, 6);
            }
        }
        g_hook_p[i] = NULL;
    }
}

// ---- CreateFile IAT 钩子 ----
typedef HANDLE (WINAPI *PFN_CreateFileA)(LPCSTR, DWORD, DWORD, LPSECURITY_ATTRIBUTES, DWORD, DWORD, HANDLE);
typedef HANDLE (WINAPI *PFN_CreateFileW)(LPCWSTR, DWORD, DWORD, LPSECURITY_ATTRIBUTES, DWORD, DWORD, HANDLE);
static PFN_CreateFileA g_origCFA;
static PFN_CreateFileW g_origCFW;

static int diag_interesting(const char* path) {
    // 大小写不敏感的包含判断：s2a / lang / cscv
    static const char* keys[3] = {"s2a", "lang", "cscv"};
    for (int k = 0; k < 3; k++) {
        const char* key = keys[k];
        size_t kl = lstrlenA(key);
        for (const char* q = path; *q; q++) {
            int m = 1;
            for (size_t j = 0; j < kl; j++) {
                char c = q[j];
                if (!c) { m = 0; break; }
                if (c >= 'A' && c <= 'Z') c = (char)(c - 'A' + 'a');
                if (c != key[j]) { m = 0; break; }
            }
            if (m) return 1;
        }
    }
    return 0;
}

HANDLE WINAPI HookCreateFileA(LPCSTR name, DWORD acc, DWORD share, LPSECURITY_ATTRIBUTES sa,
                              DWORD disp, DWORD flags, HANDLE tmpl) {
    if (name && diag_interesting(name))
        diagln("OPEN %s", name);
    return g_origCFA ? g_origCFA(name, acc, share, sa, disp, flags, tmpl)
                     : CreateFileA(name, acc, share, sa, disp, flags, tmpl);
}

HANDLE WINAPI HookCreateFileW(LPCWSTR name, DWORD acc, DWORD share, LPSECURITY_ATTRIBUTES sa,
                              DWORD disp, DWORD flags, HANDLE tmpl) {
    if (name) {
        char mb[520];
        if (WideCharToMultiByte(CP_ACP, 0, name, -1, mb, sizeof(mb), NULL, NULL) > 0
            && diag_interesting(mb))
            diagln("OPEN %s", mb);
    }
    return g_origCFW ? g_origCFW(name, acc, share, sa, disp, flags, tmpl)
                     : CreateFileW(name, acc, share, sa, disp, flags, tmpl);
}

// ---- CompareStringW（kernel32 导入，宽字符/区域感知比较）IAT 钩子 ----
typedef int (WINAPI *PFN_CompareStringW)(LCID, DWORD, LPCWSTR, int, LPCWSTR, int);
static PFN_CompareStringW g_origCSW;

__attribute__((noinline))
static void log_wide_cmp(DWORD caller, LPCWSTR w1, LPCWSTR w2) {
    if (!g_diag || !g_diagf || !w1 || !w2) return;
    char m1[200], m2[200];
    if (WideCharToMultiByte(CP_ACP, 0, w1, -1, m1, sizeof(m1), NULL, NULL) <= 0) return;
    if (WideCharToMultiByte(CP_ACP, 0, w2, -1, m2, sizeof(m2), NULL, NULL) <= 0) return;
    if (!rec_begin('W', caller, m1, m2, 0xFFFFFFFFu)) return;
    char e1[96], e2[96];
    diag_esc(e1, sizeof(e1), m1, 48);
    diag_esc(e2, sizeof(e2), m2, 48);
    diagln("W caller=0x%08X s1=\"%s\" s2=\"%s\"", (unsigned)caller, e1, e2);
}

__attribute__((noinline))
int WINAPI HookCompareStringW(LCID lc, DWORD fl, LPCWSTR s1, int c1, LPCWSTR s2, int c2) {
    log_wide_cmp((DWORD)(uintptr_t)__builtin_return_address(0), s1, s2);
    if (g_origCSW) return g_origCSW(lc, fl, s1, c1, s2, c2);
    return 0;
}

// 模块名等价比较：忽略大小写，且 ".dll" 后缀视为等价（kernel32 / kernel32.dll）
static int mod_match(const char* a, const char* b) {
    for (;;) {
        char ca = *a, cb = *b;
        if (ca >= 'A' && ca <= 'Z') ca = (char)(ca - 'A' + 'a');
        if (cb >= 'A' && cb <= 'Z') cb = (char)(cb - 'A' + 'a');
        if (ca == '.') ca = 0;
        if (cb == '.') cb = 0;
        if (ca != cb) return 0;
        if (!ca) return 1;
        a++; b++;
    }
}

static int iat_replace(DWORD base, const char* modName, const char* fnName, void* hookFn, void** origOut) {
    IMAGE_DOS_HEADER* dos = (IMAGE_DOS_HEADER*)(uintptr_t)base;
    if (dos->e_magic != IMAGE_DOS_SIGNATURE) return 0;
    IMAGE_NT_HEADERS32* nt = (IMAGE_NT_HEADERS32*)(uintptr_t)(base + dos->e_lfanew);
    if (nt->Signature != IMAGE_NT_SIGNATURE) return 0;
    DWORD impRva = nt->OptionalHeader.DataDirectory[IMAGE_DIRECTORY_ENTRY_IMPORT].VirtualAddress;
    if (!impRva) return 0;
    IMAGE_IMPORT_DESCRIPTOR* imp = (IMAGE_IMPORT_DESCRIPTOR*)(uintptr_t)(base + impRva);
    int done = 0;
    for (; imp->Name; imp++) {
        const char* mod = (const char*)(uintptr_t)(base + imp->Name);
        if (!mod_match(mod, modName)) continue;
        if (!imp->OriginalFirstThunk) continue;  // 绑定导入无名字信息，跳过以免误解析
        DWORD oftRva = imp->OriginalFirstThunk;
        IMAGE_THUNK_DATA32* oft = (IMAGE_THUNK_DATA32*)(uintptr_t)(base + oftRva);
        IMAGE_THUNK_DATA32* ft = (IMAGE_THUNK_DATA32*)(uintptr_t)(base + imp->FirstThunk);
        for (; oft->u1.Function; oft++, ft++) {
            if (oft->u1.Ordinal & IMAGE_ORDINAL_FLAG32) continue;
            IMAGE_IMPORT_BY_NAME* ibn = (IMAGE_IMPORT_BY_NAME*)(uintptr_t)(base + oft->u1.AddressOfData);
            if (lstrcmpA((const char*)ibn->Name, fnName) != 0) continue;
            DWORD old = 0;
            if (!VirtualProtect(&ft->u1.Function, 4, PAGE_READWRITE, &old)) continue;
            if (origOut) *origOut = (void*)(uintptr_t)ft->u1.Function;
            ft->u1.Function = (DWORD)(uintptr_t)hookFn;
            VirtualProtect(&ft->u1.Function, 4, old, &old);
            done = 1;
        }
    }
    return done;
}

// ---- 崩溃 / 退出日志 --------------------------------------------------------
// 目的：定位"改动数据后游戏在何时、何地"崩溃。
// 崩溃处理器运行在异常上下文里：严禁调用 CRT（fprintf/sprintf/malloc/…），
// 否则可能在崩溃处理中再次崩溃。因此全部输出只走 raw_* 裸写函数：
// 预打开的文件句柄 + WriteFile + 栈上小缓冲，无 CRT、无分配。
// 栈扫描（识别返回地址）不用 MSVC 的 __try/__except —— zig 的 clang 在
// x86-windows-gnu 目标下不支持该关键字（已实测），改用 VirtualQuery 逐页守卫。
static HANDLE g_logh = INVALID_HANDLE_VALUE;   // 预打开日志句柄（崩溃期唯一输出通道）
static PVOID  g_veh = NULL;                    // VEH 句柄
static DWORD  g_textLo = 0, g_textHi = 0;      // exe .text 节绝对地址区间 [lo,hi)
static volatile LONG g_veh_in = 0;             // VEH 重入保护
static volatile LONG g_in_exit = 0;            // Exit/Terminate 钩子递归保护

// 裸写：无 CRT、无分配、无格式化库
static DWORD raw_len(const char* s) { const char* p = s; while (*p) p++; return (DWORD)(p - s); }
static void raw_puts(HANDLE h, const char* s) { DWORD w; if (s && *s) WriteFile(h, s, raw_len(s), &w, NULL); }
static void raw_hex(HANDLE h, DWORD v) {
    char b[8];
    for (int i = 0; i < 8; i++) {
        int d = (int)((v >> (28 - 4 * i)) & 0xF);
        b[i] = (char)(d < 10 ? '0' + d : 'A' + d - 10);
    }
    DWORD w; WriteFile(h, b, 8, &w, NULL);
}
static void raw_end(HANDLE h) { SetFilePointer(h, 0, NULL, FILE_END); }

// 原始栈扫描：从 sp 起 0x400 字节内，逐 dword，记录值落在 exe .text 区间者（粗略调用链）。
// 逐页 VirtualQuery 守卫；最多 64 条命中。全程 WriteFile 裸写。
static void diag_stack_scan_raw(HANDLE h, DWORD sp) {
    if (h == INVALID_HANDLE_VALUE) return;
    raw_end(h);
    raw_puts(h, "STACK SCAN sp=0x"); raw_hex(h, sp); raw_puts(h, "\r\n");
    DWORD logged = 0, pageEnd = 0, pageOk = 0;
    for (DWORD a = sp; a < sp + 0x400 && logged < 64; a += 4) {
        if (a >= pageEnd) {
            MEMORY_BASIC_INFORMATION mbi;
            if (VirtualQuery((LPCVOID)(uintptr_t)a, &mbi, sizeof(mbi)) != sizeof(mbi)) break;
            pageEnd = (a & ~0xFFFu) + 0x1000;
            pageOk = (mbi.State == MEM_COMMIT) && !(mbi.Protect & (PAGE_NOACCESS | PAGE_GUARD));
        }
        if (!pageOk) continue;
        DWORD v = *(volatile DWORD*)(uintptr_t)a;
        if (v >= g_textLo && v < g_textHi) {
            raw_puts(h, "  [0x"); raw_hex(h, a); raw_puts(h, "] .text 0x"); raw_hex(h, v); raw_puts(h, "\r\n");
            logged++;
        }
    }
}

// VEH：记录异常码/异常地址/完整 CONTEXT，再扫描栈找 .text 返回地址；绝不吞异常。
static LONG CALLBACK DiagVeh(PEXCEPTION_POINTERS ep) {
    if (!g_diag || !ep) return EXCEPTION_CONTINUE_SEARCH;
    if (InterlockedExchange(&g_veh_in, 1)) return EXCEPTION_CONTINUE_SEARCH;  // 嵌套异常：不再处理，直接放行
    HANDLE h = g_logh;
    if (h != INVALID_HANDLE_VALUE && ep->ExceptionRecord && ep->ContextRecord) {
        PEXCEPTION_RECORD er = ep->ExceptionRecord;
        PCONTEXT c = ep->ContextRecord;
        raw_end(h);
        raw_puts(h, "EXCEPTION code=0x"); raw_hex(h, er->ExceptionCode);
        raw_puts(h, " flags=0x");        raw_hex(h, er->ExceptionFlags);
        raw_puts(h, " addr=0x");         raw_hex(h, (DWORD)(uintptr_t)er->ExceptionAddress);
        raw_puts(h, "\r\n  Eip="); raw_hex(h, c->Eip);
        raw_puts(h, " Ebp=");      raw_hex(h, c->Ebp);
        raw_puts(h, " Esp=");      raw_hex(h, c->Esp);
        raw_puts(h, " Eax=");      raw_hex(h, c->Eax);
        raw_puts(h, " Ebx=");      raw_hex(h, c->Ebx);
        raw_puts(h, " Ecx=");      raw_hex(h, c->Ecx);
        raw_puts(h, " Edx=");      raw_hex(h, c->Edx);
        raw_puts(h, " Esi=");      raw_hex(h, c->Esi);
        raw_puts(h, " Edi=");      raw_hex(h, c->Edi);
        raw_puts(h, "\r\n");
        diag_stack_scan_raw(h, c->Esp);
    }
    InterlockedExchange(&g_veh_in, 0);
    return EXCEPTION_CONTINUE_SEARCH;   // 必须放行，让异常继续传播
}

typedef void (WINAPI *PFN_ExitProcess)(UINT);
typedef BOOL (WINAPI *PFN_TerminateProcess)(HANDLE, UINT);
static PFN_ExitProcess      g_origExitProcess;
static PFN_TerminateProcess g_origTerminateProcess;

static DWORD diag_cur_esp(void) {
    DWORD sp = 0;
    __asm__ __volatile__("movl %%esp, %0" : "=r"(sp));
    return sp;
}

void WINAPI HookExitProcess(UINT code) {
    if (g_diag && !InterlockedExchange(&g_in_exit, 1)) {
        diagln("EXIT ExitProcess(code=%u)", (unsigned)code);
        diag_stack_scan_raw(g_logh, diag_cur_esp());
    }
    if (g_origExitProcess) g_origExitProcess(code);
    else ExitProcess(code);   // 原指针为空时直接调用，无递归（IAT 钩子只装在 exe 上）
}

BOOL WINAPI HookTerminateProcess(HANDLE proc, UINT code) {
    if (g_diag && !InterlockedExchange(&g_in_exit, 1)) {
        diagln("EXIT TerminateProcess(code=%u)", (unsigned)code);
        diag_stack_scan_raw(g_logh, diag_cur_esp());
    }
    if (g_origTerminateProcess) return g_origTerminateProcess(proc, code);
    return TerminateProcess(proc, code);
}

static void diag_init(DWORD exeBase) {
    char mk[MAX_PATH];
    lstrcpyA(mk, g_dir);
    lstrcatA(mk, "\\hm2zh_diag.on");
    char env[8];
    BOOL viaEnv = GetEnvironmentVariableA("HM2ZH_DIAG", env, sizeof(env)) > 0;
    if (!viaEnv && GetFileAttributesA(mk) == INVALID_FILE_ATTRIBUTES) return;

    char lp[MAX_PATH];
    lstrcpyA(lp, g_dir);
    lstrcatA(lp, "\\hm2zh_diag.log");
    g_diagf = fopen(lp, "w");
    if (!g_diagf) return;
    g_diag = 1;

    DWORD imageBase = 0x400000;
    IMAGE_DOS_HEADER* dos = (IMAGE_DOS_HEADER*)(uintptr_t)exeBase;
    if (dos->e_magic == IMAGE_DOS_SIGNATURE) {
        IMAGE_NT_HEADERS32* nt = (IMAGE_NT_HEADERS32*)(uintptr_t)(exeBase + dos->e_lfanew);
        if (nt->Signature == IMAGE_NT_SIGNATURE) imageBase = nt->OptionalHeader.ImageBase;
        // exe .text 节的绝对地址区间：栈扫描据此识别返回地址
        if (nt->Signature == IMAGE_NT_SIGNATURE) {
            IMAGE_SECTION_HEADER* sec = IMAGE_FIRST_SECTION(nt);
            for (unsigned i = 0; i < nt->FileHeader.NumberOfSections; i++) {
                if (memcmp(sec[i].Name, ".text", 5) == 0) {
                    g_textLo = exeBase + sec[i].VirtualAddress;
                    g_textHi = g_textLo + sec[i].Misc.VirtualSize;
                    break;
                }
            }
        }
    }
    diagln("=== hm2zh diag === exeBase=0x%08X imageBase=0x%08X", (unsigned)exeBase, (unsigned)imageBase);

    // 离线反解得到的入口前几字节（运行时逐字节复核，不符即安全放弃该钩子）
    static const unsigned char EX_SN[6]  = {0x53, 0x56, 0x8B, 0x4C, 0x24, 0x0C};            // strncmp
    static const unsigned char EX_CMP[8] = {0x8B, 0x54, 0x24, 0x04, 0x8B, 0x4C, 0x24, 0x08}; // strcmp
    static const unsigned char EX_CMP2[6] = {0x55, 0x8B, 0xEC, 0x8B, 0x55, 0x0C};           // strcmp（第二份）
    static const unsigned char EX_SS[8]  = {0x8B, 0x4C, 0x24, 0x08, 0x8B, 0x44, 0x24, 0x04}; // strstr
    // 名字哈希函数入口前 7 字节（0x46C070 / 0x46C0C0 同构）：push esi; mov esi,ecx; test esi,esi; jne +4
    static const unsigned char EX_HASH[7] = {0x56, 0x8B, 0xF1, 0x85, 0xF6, 0x75, 0x04};
    int okSn = install_cmp_hook(exeBase, imageBase, 0x54CC00, 0x54CC06, EX_SN,   6, (void*)&LogCmp3,   3, "strncmp");
    install_cmp_hook(exeBase, imageBase, 0x552E40, 0x552E48, EX_CMP,  8, (void*)&LogCmp2,   2, "strcmp");
    install_cmp_hook(exeBase, imageBase, 0x561810, 0x561816, EX_CMP2, 6, (void*)&LogCmp2,   2, "strcmp2");
    install_cmp_hook(exeBase, imageBase, 0x54B7C0, 0x54B7C8, EX_SS,   8, (void*)&LogStrstr, 2, "strstr");

    // 名字哈希函数：字符串指针在 ECX、入口含短跳，走专用安装器。
    // resumeVa = 分支目标（非空路径）：0x46C070+11=0x46C07B / 0x46C0C0+11=0x46C0CB。
    int okHash   = install_hash_hook(exeBase, imageBase, 0x46C070, 0x46C07B, EX_HASH, (void*)&LogNameHash, "hash");
    int okHashCi = install_hash_hook(exeBase, imageBase, 0x46C0C0, 0x46C0CB, EX_HASH, (void*)&LogNameHash, "hashci");
    diagln("NAMEHOOK strncmp=%s hash=%s hashci=%s",
           okSn ? "OK" : "MISS", okHash ? "OK" : "MISS", okHashCi ? "OK" : "MISS");

    int cw = iat_replace(exeBase, "kernel32.dll", "CompareStringW", (void*)&HookCompareStringW, (void**)&g_origCSW);
    int w = iat_replace(exeBase, "kernel32.dll", "CreateFileW", (void*)&HookCreateFileW, (void**)&g_origCFW);
    int a = iat_replace(exeBase, "kernel32.dll", "CreateFileA", (void*)&HookCreateFileA, (void**)&g_origCFA);
    diagln("IAT CompareStringW=%s CreateFileW=%s CreateFileA=%s",
           cw ? "OK" : "MISS", w ? "OK" : "MISS", a ? "OK" : "MISS");

    // ---- 崩溃 / 退出日志：预打开裸写句柄 → 装 VEH → 钩 ExitProcess/TerminateProcess ----
    // 句柄共享模式含 FILE_SHARE_WRITE：须与仍在打开的 g_diagf(FILE*) 共存，否则共享冲突。
    g_logh = CreateFileA(lp, GENERIC_WRITE, FILE_SHARE_READ | FILE_SHARE_WRITE,
                         NULL, OPEN_ALWAYS, FILE_ATTRIBUTE_NORMAL, NULL);
    g_veh = AddVectoredExceptionHandler(1, DiagVeh);   // first=1：尽早看到异常
    diagln("VEH=%s 崩溃日志句柄=%s .text=0x%08X..0x%08X",
           g_veh ? "OK" : "FAIL", g_logh != INVALID_HANDLE_VALUE ? "OK" : "FAIL",
           (unsigned)g_textLo, (unsigned)g_textHi);
    int ep = iat_replace(exeBase, "kernel32.dll", "ExitProcess", (void*)&HookExitProcess, (void**)&g_origExitProcess);
    int tp = iat_replace(exeBase, "kernel32.dll", "TerminateProcess", (void*)&HookTerminateProcess, (void**)&g_origTerminateProcess);
    diagln("IAT ExitProcess=%s TerminateProcess=%s", ep ? "OK" : "MISS", tp ? "OK" : "MISS");
}

// ---------------------------------------------------------------- 入口
// 注意：不能加 static——CRT 的 _DllMainCRTStartup 按外部符号引用 DllMain，
// static 会导致链接器采用 CRT 自带的空默认实现，我们的初始化永远不会执行。
BOOL WINAPI DllMain(HINSTANCE h, DWORD reason, LPVOID rsv) {
    (void)rsv;
    if (reason == DLL_PROCESS_ATTACH) {
        DisableThreadLibraryCalls(h);
        char path[MAX_PATH];
        GetModuleFileNameA(h, path, MAX_PATH);
        char* c = strrchr(path, '\\');
        if (c) *c = 0;
        lstrcpynA(g_dir, path, MAX_PATH);

        // 先清空上次运行的日志（须在任何 logln 之前），再加载系统 dinput8
        log_truncate();

        // 加载系统真 dinput8（绝对路径，绝对不会再递归到本代理）
        char sys[MAX_PATH], real[MAX_PATH];
        GetSystemDirectoryA(sys, MAX_PATH);
        lstrcpyA(real, sys);
        lstrcatA(real, "\\dinput8.dll");
        HMODULE hReal = LoadLibraryA(real);
        if (hReal) {
            g_pDirectInput8Create  = (PFN_DirectInput8Create)GetProcAddress(hReal, "DirectInput8Create");
            g_pDllGetClassObject   = (PFN_DllGetClassObject)GetProcAddress(hReal, "DllGetClassObject");
            g_pDllCanUnloadNow     = (PFN_HRESULT0)GetProcAddress(hReal, "DllCanUnloadNow");
            g_pDllRegisterServer   = (PFN_HRESULT0)GetProcAddress(hReal, "DllRegisterServer");
            g_pDllUnregisterServer = (PFN_HRESULT0)GetProcAddress(hReal, "DllUnregisterServer");
            logln("系统 dinput8 已加载: %s (DirectInput8Create=%s)",
                  real, g_pDirectInput8Create ? "OK" : "MISSING");
        } else {
            logln("WARN: 系统 dinput8 加载失败 (GetLastError=%u)，输入转发不可用", (unsigned)GetLastError());
        }

        // 诊断插桩（仅当标记文件/环境变量存在时生效），须尽早安装以覆盖游戏启动期的查找
        diag_init((DWORD)(uintptr_t)GetModuleHandleA(NULL));

        HANDLE t = CreateThread(NULL, 0, PatchThread, NULL, 0, NULL);
        if (t) CloseHandle(t);
    } else if (reason == DLL_PROCESS_DETACH) {
        if (g_veh) { RemoveVectoredExceptionHandler(g_veh); g_veh = NULL; }
        unhook_all();
        if (g_logh != INVALID_HANDLE_VALUE) { CloseHandle(g_logh); g_logh = INVALID_HANDLE_VALUE; }
        if (g_diagf) { fclose(g_diagf); g_diagf = NULL; }
    }
    return TRUE;
}
