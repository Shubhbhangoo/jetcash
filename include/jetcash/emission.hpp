#pragma once
#include <algorithm>
#include <cstdint>

// Shared verbatim with the C++ daemon. No floating-point consensus arithmetic.
namespace jetcash_policy {
constexpr std::uint64_t coin = 100'000'000;
constexpr std::uint64_t cap = 10'000'000 * coin;
constexpr std::uint64_t interval = 1'000'000;
constexpr std::uint64_t eras = 29;
constexpr std::uint64_t last_height = eras * interval + 1;
constexpr std::uint64_t issued(std::uint64_t height) noexcept {
    if (height >= last_height) return cap;
    std::uint64_t total = 0;
    for (std::uint64_t era = 0; era < eras && height; ++era) {
        const auto blocks = std::min(height, interval);
        total += blocks * ((5 * coin) >> era);
        height -= blocks;
    }
    return total;
}
constexpr std::uint64_t subsidy(std::uint64_t height) noexcept {
    return height == 0 || height > last_height ? 0 : issued(height) - issued(height - 1);
}
}
