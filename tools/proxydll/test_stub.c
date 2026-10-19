// test_stub.c — 离线自测内联钩子 stub（32 位，zig cc 构建）
//
// 覆盖两种 stub 形态（与 proxydll/main.c install_cmp_hook 逐字节同构）：
//   A) 3 参（strncmp 族）：把原版 HMH2.exe 里 0x54CC00 起的整段 strncmp 机器码搬到 RWX
//      缓冲 B，在 B[0] 打 6 字节 E9 补丁，验证参数传递与返回值语义。
//   B) 2 参（strcmp / strstr 族）：用 naked 汇编造一个入口前 8 字节与真 strcmp 完全一致的
//      比较函数，套用 2 参 stub，验证参数传递与返回值语义。
// 用法：test_stub.exe [HMH2.exe 路径]
#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <stdio.h>
#include <string.h>
#include <stdint.h>

#define IMG_BASE 0x400000u
#define VA_SN    0x54CC00u
#define SN_LEN   0x78u

// ---------------- 3 参：落地函数 ----------------
static volatile DWORD g_caller, g_n;
static char g_s1[160], g_s2[160];
static int g_calls;

// 与 main.c 中 LogCmp3 同签名（__cdecl），并复刻其过滤守卫
void __cdecl LogCmp3T(DWORD caller, const char* s1, const char* s2, DWORD n) {
    if (n == 0 || (n != 0xFFFFFFFFu && n > 4096)) return;
    g_caller = caller; g_n = n; g_calls++;
    snprintf(g_s1, sizeof(g_s1), "%s", s1 ? s1 : "(null)");
    snprintf(g_s2, sizeof(g_s2), "%s", s2 ? s2 : "(null)");
}

// ---------------- 2 参：落地函数 ----------------
static volatile DWORD g2_caller;
static char g2_s1[160], g2_s2[160];
static int g2_calls;

void __cdecl LogCmp2T(DWORD caller, const char* s1, const char* s2) {
    g2_caller = caller; g2_calls++;
    snprintf(g2_s1, sizeof(g2_s1), "%s", s1 ? s1 : "(null)");
    snprintf(g2_s2, sizeof(g2_s2), "%s", s2 ? s2 : "(null)");
}

// 2 参被钩函数：入口前 8 字节刻意与真 strcmp 一致（8B 44 24 04 8B 4C 24 08），
// 只用 eax/ecx/edx（不碰被调用者保存寄存器），语义 = 相等返 0 否则返 1。
__attribute__((naked, noinline, used))
static int my_cmp2(const char* a, const char* b) {
    __asm__ volatile(
        "mov 4(%esp), %eax\n\t"
        "mov 8(%esp), %ecx\n\t"
        "1:\n\t"
        "movzbl (%eax), %edx\n\t"
        "cmpb (%ecx), %dl\n\t"
        "jne 2f\n\t"
        "test %dl, %dl\n\t"
        "je 3f\n\t"
        "inc %eax\n\t"
        "inc %ecx\n\t"
        "jmp 1b\n\t"
        "2:\n\t"
        "movl $1, %eax\n\t"
        "ret\n\t"
        "3:\n\t"
        "xor %eax, %eax\n\t"
        "ret\n\t");
}

static DWORD rd32(const unsigned char* p) {
    return (DWORD)p[0] | ((DWORD)p[1] << 8) | ((DWORD)p[2] << 16) | ((DWORD)p[3] << 24);
}

static long va2off(const unsigned char* d, DWORD va) {
    DWORD pe = rd32(d + 0x3C);
    unsigned nsec = d[pe + 6] | (d[pe + 7] << 8);
    unsigned optsz = d[pe + 20] | (d[pe + 21] << 8);
    long stab = pe + 24 + optsz;
    DWORD rva = va - IMG_BASE;
    for (unsigned i = 0; i < nsec; i++) {
        const unsigned char* s = d + stab + i * 40;
        DWORD vs = rd32(s + 8), vaSec = rd32(s + 12), rs = rd32(s + 16), rp = rd32(s + 20);
        DWORD span = vs > rs ? vs : rs;
        if (rva >= vaSec && rva < vaSec + span) return (long)(rp + (rva - vaSec));
    }
    return -1;
}

static int fails = 0;
static void check(int cond, const char* what) {
    printf("  [%s] %s\n", cond ? "OK" : "FAIL", what);
    if (!cond) fails++;
}

// 按与 main.c install_cmp_hook 相同的逻辑生成 stub（返回 stub 首地址）
static unsigned char* build_stub(void* landing, unsigned char* resumeTarget,
                                 const unsigned char* replay, unsigned replayLen, unsigned nargs) {
    unsigned char* stub = (unsigned char*)VirtualAlloc(NULL, 128, MEM_COMMIT | MEM_RESERVE,
                                                       PAGE_EXECUTE_READWRITE);
    if (!stub) return NULL;
    unsigned n = 0, i, k;
    stub[n++] = 0x60;
    unsigned disp = 0x20 + 4 * nargs;
    for (i = 0; i <= nargs; i++) {
        stub[n++] = 0xFF; stub[n++] = 0x74; stub[n++] = 0x24; stub[n++] = (unsigned char)disp;
    }
    unsigned e8 = n;
    stub[n++] = 0xE8; for (k = 0; k < 4; k++) stub[n++] = 0;
    stub[n++] = 0x83; stub[n++] = 0xC4; stub[n++] = (unsigned char)(4 * (nargs + 1));
    stub[n++] = 0x61;
    memcpy(stub + n, replay, replayLen); n += replayLen;
    unsigned e9 = n;
    stub[n++] = 0xE9; for (k = 0; k < 4; k++) stub[n++] = 0;
    DWORD sb = (DWORD)(uintptr_t)stub;
    DWORD rel1 = (DWORD)(uintptr_t)landing - (sb + e8 + 5);
    DWORD rel2 = (DWORD)(uintptr_t)resumeTarget - (sb + e9 + 5);
    memcpy(stub + e8 + 1, &rel1, 4);
    memcpy(stub + e9 + 1, &rel2, 4);
    FlushInstructionCache(GetCurrentProcess(), stub, n);
    return stub;
}

// 把 p 的前 6 字节改成 E9→stub
static int patch_entry(unsigned char* p, unsigned char* stub) {
    DWORD old = 0;
    if (!VirtualProtect(p, 6, PAGE_EXECUTE_READWRITE, &old)) return 0;
    DWORD sb = (DWORD)(uintptr_t)stub;
    DWORD rel = sb - (DWORD)(uintptr_t)(p + 5);
    unsigned char code[6] = {0xE9,
                             (unsigned char)(rel & 0xFF), (unsigned char)((rel >> 8) & 0xFF),
                             (unsigned char)((rel >> 16) & 0xFF), (unsigned char)((rel >> 24) & 0xFF),
                             0x90};
    memcpy(p, code, 6);
    VirtualProtect(p, 6, old, &old);
    FlushInstructionCache(GetCurrentProcess(), p, 6);
    return 1;
}
static void restore_entry(unsigned char* p, const unsigned char* orig6) {
    DWORD old = 0;
    if (VirtualProtect(p, 6, PAGE_EXECUTE_READWRITE, &old)) {
        memcpy(p, orig6, 6);
        VirtualProtect(p, 6, old, &old);
        FlushInstructionCache(GetCurrentProcess(), p, 6);
    }
}

int main(int argc, char** argv) {
    setvbuf(stdout, NULL, _IONBF, 0);
    const char* exePath = argc > 1 ? argv[1] : "..\\..\\work\\original\\HMH2.exe";
    FILE* f = fopen(exePath, "rb");
    if (!f) { printf("FAIL: 打不开 %s\n", exePath); return 2; }
    static unsigned char d[2 * 1024 * 1024];
    size_t dlen = fread(d, 1, sizeof(d), f);
    fclose(f);
    (void)dlen;
    long off = va2off(d, VA_SN);
    if (off < 0) { printf("FAIL: VA 0x%X 无节映射\n", VA_SN); return 2; }

    // ================= A) 3 参 stub（strncmp 族）=================
    unsigned char* B = (unsigned char*)VirtualAlloc(NULL, 0x1000, MEM_COMMIT | MEM_RESERVE,
                                                    PAGE_EXECUTE_READWRITE);
    if (!B) { printf("FAIL: VirtualAlloc B\n"); return 2; }
    memcpy(B, d + off, SN_LEN);
    static const unsigned char expect3[6] = {0x53, 0x56, 0x8B, 0x4C, 0x24, 0x0C};
    check(memcmp(B, expect3, 6) == 0, "A: 目标入口 6 字节与原版一致");
    unsigned char* sb3 = build_stub((void*)&LogCmp3T, B + 6, expect3, 6, 3);
    check(sb3 != NULL, "A: stub 生成");
    patch_entry(B, sb3);

    typedef int (__cdecl *PFN3)(const char*, const char*, int);
    PFN3 fn3 = (PFN3)(void*)B;
    g_calls = 0; g_caller = 0; g_n = 0;
    int r1 = fn3("Hero Slash", "Hero Slash", 10);
    check(r1 == 0, "A: 相等串返回 0");
    check(g_calls == 1, "A: 落地函数被调用 1 次");
    check(strcmp(g_s1, "Hero Slash") == 0 && strcmp(g_s2, "Hero Slash") == 0, "A: s1/s2 参数正确");
    check(g_n == 10, "A: n 参数正确 (10)");
    check(g_caller > 0x1000 && g_caller < 0x80000000u, "A: caller 为有效代码地址");
    g_calls = 0;
    int r2 = fn3("Drain Axe", "Hero Slash", 9);
    check(r2 != 0, "A: 不等串返回非 0");
    check(strcmp(g_s1, "Drain Axe") == 0 && strcmp(g_s2, "Hero Slash") == 0, "A: 不等比较 s1/s2 正确");
    g_calls = 0;
    int r3 = fn3("aaa", "aab", 0);
    check(r3 == 0 && g_calls == 0, "A: n=0 返回 0 且不记录");
    g_calls = 0;
    int r4 = fn3("aaaa", "aaab", 3);
    check(r4 == 0 && g_calls == 1 && g_n == 3, "A: 前 n 字节相同返回 0 且记录 n=3");
    int r5 = fn3("abc", "abc", -1);
    int r6 = fn3("abc", "abd", -1);
    check(r5 == 0 && r6 != 0, "A: n=-1(全长) 语义正确");
    restore_entry(B, expect3);

    // ================= B) 2 参 stub（strcmp / strstr 族）=================
    unsigned char* p2 = (unsigned char*)(void*)&my_cmp2;
    unsigned char orig2[8];
    memcpy(orig2, p2, 8);
    static const unsigned char expect2[8] = {0x8B, 0x44, 0x24, 0x04, 0x8B, 0x4C, 0x24, 0x08};
    check(memcmp(orig2, expect2, 8) == 0, "B: 被钩函数入口 8 字节与真 strcmp 同构");
    printf("    my_cmp2 = %p\n", (void*)p2);

    typedef int (__cdecl *PFN2)(const char*, const char*);
    PFN2 fn2 = my_cmp2;
    // 未挂钩基线
    check(fn2("abc", "abc") == 0, "B(基线): 相等返 0");
    check(fn2("abc", "abd") != 0, "B(基线): 不等返非 0");

    unsigned char* sb2 = build_stub((void*)&LogCmp2T, p2 + 8, expect2, 8, 2);
    check(sb2 != NULL, "B: stub 生成");
    check(patch_entry(p2, sb2), "B: 入口补丁写入");
    check(memcmp(p2, expect2, 6) != 0, "B: 入口已被 E9 改写");

    g2_calls = 0; g2_caller = 0;
    int s1r = fn2("Hero Slash", "Hero Slash");
    check(s1r == 0, "B: 挂钩后相等仍返 0（语义保持）");
    check(g2_calls == 1, "B: 落地函数被调用 1 次");
    check(strcmp(g2_s1, "Hero Slash") == 0 && strcmp(g2_s2, "Hero Slash") == 0, "B: s1/s2 参数正确");
    check(g2_caller > 0x1000 && g2_caller < 0x80000000u, "B: caller 为有效代码地址");

    g2_calls = 0;
    int s2r = fn2("Drain Axe", "Hero Slash");
    check(s2r != 0, "B: 挂钩后不等仍返非 0");
    check(strcmp(g2_s1, "Drain Axe") == 0 && strcmp(g2_s2, "Hero Slash") == 0, "B: 不等比较 s1/s2 正确");

    restore_entry(p2, orig2);
    check(memcmp(p2, expect2, 6) == 0, "B: 还原后入口恢复");
    check(fn2("abc", "abc") == 0, "B: 还原后语义恢复");

    printf(fails == 0 ? "== STUB SELF-TEST: PASS ==\n" : "== STUB SELF-TEST: FAIL (%d) ==\n", fails);
    return fails ? 1 : 0;
}
