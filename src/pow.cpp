#include "jetcash/pow.hpp"
#include <algorithm>
#include <stdexcept>
#ifdef JETCASH_HAS_RANDOMX
#include <randomx.h>
#endif

namespace jetcash {
struct RandomXHasher::Impl {
#ifdef JETCASH_HAS_RANDOMX
    randomx_cache* cache = nullptr;
    randomx_vm* vm = nullptr;
    ~Impl() {
        if (vm) randomx_destroy_vm(vm);
        if (cache) randomx_release_cache(cache);
    }
#endif
};

bool randomx_available() noexcept {
#ifdef JETCASH_HAS_RANDOMX
    return true;
#else
    return false;
#endif
}

RandomXHasher::RandomXHasher(const Hash& ancestor_seed) : impl_(std::make_unique<Impl>()) {
#ifdef JETCASH_HAS_RANDOMX
    // Portable light verification mode; no executable JIT or huge-page requirement.
    impl_->cache = randomx_alloc_cache(RANDOMX_FLAG_DEFAULT);
    if (!impl_->cache) throw std::runtime_error("RandomX cache allocation failed");
    randomx_init_cache(impl_->cache, ancestor_seed.data(), ancestor_seed.size());
    impl_->vm = randomx_create_vm(RANDOMX_FLAG_DEFAULT, impl_->cache, nullptr);
    if (!impl_->vm) throw std::runtime_error("RandomX VM allocation failed");
#else
    (void)ancestor_seed;
    throw std::runtime_error("RandomX disabled in this build");
#endif
}
RandomXHasher::~RandomXHasher() = default;

Hash RandomXHasher::hash(std::span<const std::uint8_t> header) {
    if (header.empty() || header.size() > 4096)
        throw std::invalid_argument("header size must be 1..4096 bytes");
#ifdef JETCASH_HAS_RANDOMX
    Hash result{};
    randomx_calculate_hash(impl_->vm, header.data(), header.size(), result.data());
    return result;
#else
    throw std::runtime_error("RandomX disabled in this build");
#endif
}

bool meets_target(const Hash& hash, const Hash& target) noexcept {
    if (std::all_of(target.begin(), target.end(), [](auto b) { return b == 0; })) return false;
    for (std::size_t i = hash.size(); i-- > 0;) {
        if (hash[i] < target[i]) return true;
        if (hash[i] > target[i]) return false;
    }
    return true;
}
}
