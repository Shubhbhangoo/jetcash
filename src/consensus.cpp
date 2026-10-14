#include "jetcash/consensus.hpp"
#include "jetcash/emission.hpp"
#include <algorithm>
#include <iomanip>
#include <sstream>

namespace jetcash {
Amount issued_supply(std::uint64_t height) noexcept {
    return jetcash_policy::issued(height);
}

Amount block_subsidy(std::uint64_t height) noexcept {
    return jetcash_policy::subsidy(height);
}

std::string format_amount(Amount value) {
    std::ostringstream out;
    out << value / coin << '.' << std::setw(8) << std::setfill('0') << value % coin;
    return out.str();
}

RewardCheck check_reward(std::uint64_t height, Amount minted_before,
                         Amount fees, Amount claimed_reward) noexcept {
    if (height == 0) return {false, "genesis cannot claim a reward"};
    if (minted_before != issued_supply(height - 1))
        return {false, "issued supply does not match validated height"};
    const Amount subsidy = block_subsidy(height);
    if (subsidy > max_supply - minted_before)
        return {false, "supply cap exceeded"};
    // A valid fee total cannot exceed the already issued money supply.
    if (fees > minted_before) return {false, "fees exceed existing supply"};
    if (claimed_reward != subsidy + fees)
        return {false, "reward must equal subsidy plus validated fees"};
    return {true, "ok"};
}

std::uint64_t randomx_seed_height(std::uint64_t height) noexcept {
    constexpr std::uint64_t epoch = 2048;
    constexpr std::uint64_t lag = 64;
    if (height <= epoch + lag) return 0;
    return ((height - lag - 1) / epoch) * epoch;
}

ShieldedStatus shielded_status() noexcept { return ShieldedStatus::backend_unavailable; }
}
