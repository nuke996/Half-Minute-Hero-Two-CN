// test_host.c v3 — 32 位测试宿主：确定性端到端验证 dinput8 代理 DLL 补丁逻辑
// 方案：与 ASLR/64KB 粒度完全解耦
//   1) VirtualAlloc(NULL) 一块 1MB 内存 A（任意地址）
//   2) 把 HMH2.exe.bak 的 VA 0x4D8000..0x4DA000 内容放到 A + (VA-0x400000)
//   3) 改写补丁数据：header.imagebase := 宿主基址, 各记录 va += (A - 0x400000)
//      ⇒ DLL 算式 addr = exeBase + (va - imagebase) 恰好落在模拟页
//   4) 预占 0x5F4000/0x8000（让 DLL 的固定分配成功，回填值与 T7 完全一致）
//   5) SetEnvironmentVariable HM2ZH_PATCH=test_patch.bin → LoadLibrary（绝对路径）
//   6) 回读模拟页与 HMH2.exe（T7 态）逐字节比对，DIFF=0 为 PASS
#include <windows.h>
#include <stdio.h>
#include <string.h>

#define VA_LO 0x4D8000u
#define VA_HI 0x4DA000u
#define PREFERRED_BASE 0x400000u
#define FO(va) (0x400u + ((va) - 0x401000u))   // VA -> file offset（.text 节）

static unsigned char g_orig[VA_HI - VA_LO];
static unsigned char g_t7[VA_HI - VA_LO];
static unsigned char g_bin[64 * 1024];

static DWORD rd32(const unsigned char* p) {
    return (DWORD)p[0] | ((DWORD)p[1] << 8) | ((DWORD)p[2] << 16) | ((DWORD)p[3] << 24);
}
static void wr32(unsigned char* p, DWORD v) {
    p[0] = (unsigned char)(v & 0xFF);
    p[1] = (unsigned char)((v >> 8) & 0xFF);
    p[2] = (unsigned char)((v >> 16) & 0xFF);
    p[3] = (unsigned char)((v >> 24) & 0xFF);
}

int main(void) {
    setvbuf(stdout, NULL, _IONBF, 0);   // 崩溃也不丢输出

    FILE* fb = fopen("..\\..\\HMH2.exe.bak", "rb");
    FILE* fc = fopen("..\\..\\HMH2.exe", "rb");
    if (!fb || !fc) { printf("FAIL: 打不开 HMH2.exe.bak / HMH2.exe\n"); return 1; }
    fseek(fb, FO(VA_LO), SEEK_SET); fread(g_orig, 1, sizeof(g_orig), fb); fclose(fb);
    fseek(fc, FO(VA_LO), SEEK_SET); fread(g_t7, 1, sizeof(g_t7), fc); fclose(fc);

    // ---- 1) 分配模拟块 ----
    unsigned char* A = (unsigned char*)VirtualAlloc(NULL, 0x100000u, MEM_RESERVE | MEM_COMMIT, PAGE_EXECUTE_READWRITE);
    if (!A) { printf("FAIL: VirtualAlloc A (err=%u)\n", (unsigned)GetLastError()); return 1; }
    printf("模拟块 A = 0x%08X (1MB)\n", (unsigned)(uintptr_t)A);
    memset(A, 0, 0x100000u);
    memcpy(A + (VA_LO - PREFERRED_BASE), g_orig, sizeof(g_orig));

    // ---- 4) 不预占 atbl——让 DLL 自己走固定路径 reserve 0x5F0000+commit 0x5F4000，
    //         回填值与 T7 完全一致（回退路径已在上轮测试中验证自洽）----

    // ---- 2/3) 生成重定基的 test_patch.bin ----
    FILE* fp = fopen("hm2zh_patch.bin", "rb");
    if (!fp) { printf("FAIL: 打不开 hm2zh_patch.bin\n"); return 1; }
    size_t binLen = fread(g_bin, 1, sizeof(g_bin), fp);
    fclose(fp);
    if (binLen < 16 || memcmp(g_bin, "H2ZP", 4) != 0) { printf("FAIL: 补丁文件魔数\n"); return 1; }
    HMODULE self = GetModuleHandleA(NULL);
    DWORD exeBase = (DWORD)(uintptr_t)self;
    DWORD shift = (DWORD)(uintptr_t)A - PREFERRED_BASE;
    wr32(g_bin + 8, exeBase);                       // header.imagebase := 宿主基址 ⇒ DLL 内 delta=0
    unsigned count = rd32(g_bin + 12);
    size_t off = 16;
    for (unsigned i = 0; i < count; i++) {
        unsigned char* rec = g_bin + off;
        off += 16;
        unsigned char type = rec[0], len = rec[1], window = rec[2];
        DWORD va = rd32(rec + 4);
        wr32(rec + 4, va + shift);                  // va += (A - 0x400000)
        if (type == 1) off += (size_t)len * 2;
        // type2 无附加数据
        (void)window;
    }
    if (off != binLen) { printf("WARN: 补丁文件尾部 %zu 字节未消费\n", binLen - off); }
    FILE* fo = fopen("test_patch.bin", "wb");
    fwrite(g_bin, 1, binLen, fo);
    fclose(fo);

    // ---- 5) 设置环境变量并加载代理 DLL（绝对路径，排除搜索顺序歧义）----
    SetEnvironmentVariableA("HM2ZH_PATCH", "test_patch.bin");
    DeleteFileA("hm2zh_patch.log");
    char dllPath[MAX_PATH], selfPath[MAX_PATH];
    GetModuleFileNameA(NULL, selfPath, MAX_PATH);
    char* slash = strrchr(selfPath, '\\');
    if (slash) *slash = 0;
    snprintf(dllPath, sizeof(dllPath), "%s\\dinput8.dll", selfPath);
    HMODULE h = LoadLibraryA(dllPath);
    if (!h) { printf("FAIL: LoadLibraryA(%s) err=%u\n", dllPath, (unsigned)GetLastError()); return 2; }
    char mp[MAX_PATH] = {0};
    GetModuleFileNameA(h, mp, MAX_PATH);
    printf("加载的模块: %s\n", mp);
    FARPROC f = GetProcAddress(h, "DirectInput8Create");
    printf("DirectInput8Create 导出 -> %p %s\n", (void*)f, f ? "(OK)" : "(MISSING!)");

    Sleep(2500);   // 等补丁线程

    // ---- 6) 回读比对 ----
    int diff = 0, first = -1;
    unsigned char* mem = A + (VA_LO - PREFERRED_BASE);
    for (size_t i = 0; i < sizeof(g_t7); i++) {
        if (mem[i] != g_t7[i]) { diff++; if (first < 0) first = (int)i; }
    }
    printf("回读比对: DIFF=%d (期望 0)\n", diff);
    if (first >= 0) {
        DWORD va = VA_LO + (DWORD)first;
        printf("  首个差异 VA=0x%08X mem=%02X t7=%02X\n", va, mem[first], g_t7[first]);
    }
    printf(diff == 0 ? "== END-TO-END: PASS ==\n" : "== END-TO-END: FAIL ==\n");
    Sleep(300);
    return 0;
}
