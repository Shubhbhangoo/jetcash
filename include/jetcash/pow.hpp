#pragma once
#include <array>
#include <cstdint>
#include <memory>
#include <span>

namespace jetcash {
using Hash = std::array<std::uint8_t, 32>;
bool randomx_available() noexcept;
// One cache/VM per worker; instances must not be shared across threads.
// The caller supplies a validated ancestor seed and canonical header bytes.
class RandomXHasher {
public:
    explicit RandomXHasher(const Hash& ancestor_seed);
    ~RandomXHasher();
    RandomXHasher(const RandomXHasher&) = delete;
    RandomXHasher& operator=(const RandomXHasher&) = delete;
    Hash hash(std::span<const std::uint8_t> header);
private:
    struct Impl;
    std::unique_ptr<Impl> impl_;
};
// Hash and target are unsigned 256-bit little-endian values. Zero target is invalid.
bool meets_target(const Hash& hash, const Hash& target) noexcept;
}
