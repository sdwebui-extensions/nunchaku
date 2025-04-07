#pragma once

#include <cstdint>
#include "common.h"

// only supports cuda 12.5+

namespace nunchaku::kernels {


namespace mma_helper {
    struct f32 {
        static constexpr const char value[] = "f32";
    };
    struct f16 {
        static constexpr const char value[] = "f16";
    };
    struct bf16 {
        static constexpr const char value[] = "bf16";
    };
    struct s32 {
        static constexpr const char value[] = "s32";
    };
    struct s4 {
        static constexpr const char value[] = "s4";
    };
    struct u4 {
        static constexpr const char value[] = "u4";
    };

    template<bool is_bf16>
    using f16bf16 = std::conditional_t<is_bf16, bf16, f16>;
    template<bool is_unsigned>
    using s4u4 = std::conditional_t<is_unsigned, u4, s4>;
};

__device__ __forceinline__
static uint2 mma_m16n8k16_f16f16f16f16(uint4 a, uint2 b, uint2 c) {
    uint2 d;
#if defined(__CUDA_ARCH__) && __CUDA_ARCH__ >= 800
    asm volatile(
        "mma.sync.aligned.m16n8k16.row.col.f16.f16.f16.f16 "
        "{%0,  %1},"
        "{%2,  %3,  %4,  %5},"
        "{%6,  %7},"
        "{%8,  %9};\n"
        : 
        "=r"(d.x), "=r"(d.y)
        : 
        "r"(a.x), "r"(a.y), "r"(a.z), "r"(a.w),
        "r"(b.x), "r"(b.y),
        "r"(c.x), "r"(c.y)
    );
#else
    asm volatile(
        "{"
        ".reg .b32 tmp0, tmp1;"
        "mma.sync.aligned.m16n8k8.row.col.f16.f16.f16.f16 "
        "{tmp0,  tmp1},"
        "{%2,  %3},"
        "{%6},"
        "{%8,  %9};\n"
        "mma.sync.aligned.m16n8k8.row.col.f16.f16.f16.f16 "
        "{%0,  %1},"
        "{%4,  %5},"
        "{%7},"
        "{tmp0,  tmp1};"
        "}\n"
        : 
        "=r"(d.x), "=r"(d.y)
        : 
        "r"(a.x), "r"(a.y), "r"(a.z), "r"(a.w),
        "r"(b.x), "r"(b.y),
        "r"(c.x), "r"(c.y)
    );
#endif
    return d;
}

template<bool is_bf16>
__device__ __forceinline__
static uint4 mma_m16n8k16_f32f16f16f32(uint4 a, uint2 b, uint4 c) {
    uint4 d;
#if defined(__CUDA_ARCH__) && __CUDA_ARCH__ >= 800
    asm volatile(
        "mma.sync.aligned.m16n8k16.row.col.f32.%14.%14.f32 "
        "{%0,  %1,  %2,  %3},"
        "{%4,  %5,  %6,  %7},"
        "{%8,  %9},"
        "{%10,  %11,  %12,  %13};\n"
        : 
        "=r"(d.x), "=r"(d.y), "=r"(d.z), "=r"(d.w)
        : 
        "r"(a.x), "r"(a.y), "r"(a.z), "r"(a.w),
        "r"(b.x), "r"(b.y),
        "r"(c.x), "r"(c.y), "r"(c.z), "r"(c.w),
        "C"(mma_helper::f16bf16<is_bf16>::value)
    );
#else
    static_assert(!is_bf16);
    asm volatile(
        "{"
        ".reg .b32 tmp0, tmp1, tmp2, tmp3;"
        "mma.sync.aligned.m16n8k8.row.col.f32.f16.f16.f32 "
        "{tmp0,  tmp1,  tmp2,  tmp3},"
        "{%4,  %5},"
        "{%8},"
        "{%10,  %11,  %12,  %13};\n"
        "mma.sync.aligned.m16n8k8.row.col.f32.f16.f16.f32 "
        "{%0,  %1,  %2,  %3},"
        "{%6,  %7},"
        "{%9},"
        "{tmp0,  tmp1,  tmp2,  tmp3};"
        "}\n"
        : 
        "=r"(d.x), "=r"(d.y), "=r"(d.z), "=r"(d.w)
        : 
        "r"(a.x), "r"(a.y), "r"(a.z), "r"(a.w),
        "r"(b.x), "r"(b.y),
        "r"(c.x), "r"(c.y), "r"(c.z), "r"(c.w)
    );
#endif
    return d;
}

template<typename AType, typename BType>
__device__ __forceinline__
static uint4 mma_m16n8kx_s32common(uint4 a, uint2 b, uint4 c) {
    uint4 d;
    static constexpr int K = (std::is_same_v<AType, mma_helper::s4> || std::is_same_v<AType, mma_helper::u4>) ? 64 : 32;

#if defined(__CUDA_ARCH__) && __CUDA_ARCH__ >= 800
    asm volatile(
        "mma.sync.aligned.m16n8k%14.row.col.s32.%15.%16.s32 "
        "{%0,  %1,  %2,  %3},"
        "{%4,  %5,  %6,  %7},"
        "{%8,  %9},"
        "{%10,  %11,  %12,  %13};\n"
        : 
        "=r"(d.x), "=r"(d.y), "=r"(d.z), "=r"(d.w)
        : 
        "r"(a.x), "r"(a.y), "r"(a.z), "r"(a.w),
        "r"(b.x), "r"(b.y),
        "r"(c.x), "r"(c.y), "r"(c.z), "r"(c.w),
        "n"(K),
        "C"(AType::value),
        "C"(BType::value)
    );
#else
    asm volatile(
        "{"
        ".reg .b32 tmp0, tmp1, tmp2, tmp3;"
        "mma.sync.aligned.m8n8k%14.row.col.s32.%15.%16.s32 "
        "{tmp0, tmp1},"
        "{%4},"
        "{%8},"
        "{%10,  %11};\n"
        "mma.sync.aligned.m8n8k%14.row.col.s32.%15.%16.s32 "
        "{tmp2, tmp3},"
        "{%5},"
        "{%8},"
        "{%12,  %13};\n"
        "mma.sync.aligned.m8n8k%14.row.col.s32.%15.%16.s32 "
        "{%0,  %1},"
        "{%6},"
        "{%9},"
        "{tmp0, tmp1};\n"
        "mma.sync.aligned.m8n8k%14.row.col.s32.%15.%16.s32 "
        "{%2,  %3},"
        "{%7},"
        "{%9},"
        "{tmp2, tmp3};\n"
        "}\n"
        : 
        "=r"(d.x), "=r"(d.y), "=r"(d.z), "=r"(d.w)
        : 
        "r"(a.x), "r"(a.y), "r"(a.z), "r"(a.w),
        "r"(b.x), "r"(b.y),
        "r"(c.x), "r"(c.y), "r"(c.z), "r"(c.w),
        "n"(K / 2),
        "C"(AType::value),
        "C"(BType::value)
    );
#endif
    return d;
}
    

};  // namespace nunchaku::kernels