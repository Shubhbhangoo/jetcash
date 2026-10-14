#include "jetcash/pow.hpp"
#include <randomx.h>
#include <iostream>
#include <memory>
#include <string_view>

int main() {
    using namespace jetcash;
    using Cache = std::unique_ptr<randomx_cache, decltype(&randomx_release_cache)>;
    using VM = std::unique_ptr<randomx_vm, decltype(&randomx_destroy_vm)>;
    Cache cache(randomx_alloc_cache(RANDOMX_FLAG_DEFAULT), randomx_release_cache);
    if (!cache) return 1;
    constexpr std::string_view key = "test key 000";
    constexpr std::string_view input = "This is a test";
    randomx_init_cache(cache.get(), key.data(), key.size());
    VM vm(randomx_create_vm(RANDOMX_FLAG_DEFAULT, cache.get(), nullptr), randomx_destroy_vm);
    if (!vm) return 1;
    Hash result{};
    randomx_calculate_hash(vm.get(), input.data(), input.size(), result.data());
    // RandomX v1.2.1 src/tests/tests.cpp, hash test 2a.
    constexpr Hash expected = {0x63,0x91,0x83,0xaa,0xe1,0xbf,0x4c,0x9a,
        0x35,0x88,0x4c,0xb4,0x6b,0x09,0xca,0xd9,0x17,0x5f,0x04,0xef,
        0xd7,0x68,0x4e,0x72,0x62,0xa0,0xac,0x1c,0x2f,0x0b,0x4e,0x3f};
    if (result != expected) { std::cerr << "Upstream vector mismatch\n"; return 1; }
    // Cross-check our fixed 32-byte ancestor seed wrapper against the C API.
    vm.reset();
    Hash seed{};
    seed[0] = 42;
    randomx_init_cache(cache.get(), seed.data(), seed.size());
    vm.reset(randomx_create_vm(RANDOMX_FLAG_DEFAULT, cache.get(), nullptr));
    if (!vm) return 1;
    randomx_calculate_hash(vm.get(), input.data(), input.size(), result.data());
    vm.reset();
    cache.reset();
    RandomXHasher wrapper(seed);
    const auto wrapped = wrapper.hash({reinterpret_cast<const std::uint8_t*>(input.data()), input.size()});
    if (wrapped != result) { std::cerr << "Wrapper mismatch\n"; return 1; }
    std::cout << "Upstream vector and C++ wrapper cross-check passed\n";
}
