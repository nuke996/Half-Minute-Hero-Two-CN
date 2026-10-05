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
//   - 全程写 hm2zh_patch.log 诊断日志

#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <stdio.h>
#include <stdarg.h>
#include <string.h>

// ---------------------------------------------------------------- 日志
static char g_dir[MAX_PATH] = {0};

static void logln(const char* fmt, ...) {
    char path[MAX_PATH];
    lstrcpyA(path, g_dir);
    lstrcatA(path, "\\hm2zh_patch.log");
    FILE* f = fopen(path, "a");
    if (!f) return;
    SYSTEMTIME st;
    GetLocalTime(&st);
    fprintf(f, "[%02u:%02u:%02u.%03u] ",
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

        HANDLE t = CreateThread(NULL, 0, PatchThread, NULL, 0, NULL);
        if (t) CloseHandle(t);
    }
    return TRUE;
}
