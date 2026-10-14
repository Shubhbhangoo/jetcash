#pragma once
#include <cstdint>
#include <string>

namespace jetcash {
using Amount = std::uint64_t;
inline constexpr Amount coin = 100'000'000;
inline constexpr Amount max_supply = 10'000'000 * coin;
inline constexpr Amount initial_subsidy = 5 * coin;
inline constexpr std::uint64_t halving_interval = 1'000'000;
inline constexpr std::uint64_t target_block_seconds = 60;
inline constexpr std::uint64_t emission_eras = 29;
inline constexpr std::uint64_t final_emission_height = emission_eras * halving_interval + 1;

// Height zero is an unspendable genesis with no emission.
Amount issued_supply(std::uint64_t height) noexcept;
Amount block_subsidy(std::uint64_t height) noexcept;
std::string format_amount(Amount value);

struct RewardCheck {
    bool valid;
    const char* reason;
};
// minted_before must come from validated chain state, never from the peer.
// Fees recycle existing coins; they do not increase issued supply.
RewardCheck check_reward(std::uint64_t height, Amount minted_before,
                         Amount fees, Amount claimed_reward) noexcept;

// Draft key rotation: an ancestor key, never a miner-selected key.
std::uint64_t randomx_seed_height(std::uint64_t height) noexcept;

enum class ShieldedStatus { backend_unavailable };
// Deliberately no accept-all proof backend or plaintext transaction fallback.
ShieldedStatus shielded_status() noexcept;
}
