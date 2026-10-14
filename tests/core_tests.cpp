#include "jetcash/consensus.hpp"
#include "jetcash/pow.hpp"
#include <iostream>
#include <limits>
#include <stdexcept>
#include <string_view>

namespace {
int checks = 0;
void require(bool condition, std::string_view message) {
    ++checks;
    if (!condition) throw std::runtime_error(std::string(message));
}
}
int main() {
    using namespace jetcash;
    try {
        require(issued_supply(0) == 0 && block_subsidy(0) == 0, "no genesis emission");
        require(block_subsidy(1) == 5 * coin, "initial subsidy");
        require(block_subsidy(halving_interval) == 5 * coin, "last first-era block");
        require(block_subsidy(halving_interval + 1) == 250'000'000, "first halving");
        require(issued_supply(halving_interval) == max_supply / 2, "first-era supply");
        Amount independent_total = 0;
        for (std::uint64_t era = 0; era < emission_eras; ++era) {
            const auto start = era * halving_interval + 1;
            const auto end = (era + 1) * halving_interval;
            const auto reward = initial_subsidy >> era;
            require(block_subsidy(start) == reward && block_subsidy(end) == reward, "era boundary reward");
            independent_total += reward * halving_interval;
            require(issued_supply(end) == independent_total, "independent emission sum");
            require(issued_supply(end) <= max_supply, "cap at every era");
        }
        require(block_subsidy(final_emission_height) == max_supply - independent_total, "rounding remainder");
        require(issued_supply(final_emission_height) == max_supply, "exact cap");
        require(block_subsidy(final_emission_height + 1) == 0, "no tail emission");
        require(issued_supply(std::numeric_limits<std::uint64_t>::max()) == max_supply, "extreme height cap");
        require(block_subsidy(std::numeric_limits<std::uint64_t>::max()) == 0, "extreme height subsidy");
        require(check_reward(1, 0, 0, 5 * coin).valid, "valid initial reward");
        require(!check_reward(0, 0, 0, 0).valid, "genesis reward rejected");
        require(!check_reward(1, 0, 0, 5 * coin + 1).valid, "inflation rejected");
        require(!check_reward(1, 1, 0, 5 * coin).valid, "incorrect supply rejected");
        require(!check_reward(1, 0, std::numeric_limits<Amount>::max(), 0).valid, "overflow fee rejected");
        require(!check_reward(2, max_supply + 1, 0, 0).valid, "oversupply rejected");
        require(check_reward(2, 5 * coin, coin, 6 * coin).valid, "fees recycle supply");
        require(check_reward(final_emission_height + 1, max_supply, coin, coin).valid, "fee-only era");
        require(format_amount(max_supply) == "10000000.00000000", "integer formatting");
        require(randomx_seed_height(2112) == 0, "seed lag boundary");
        require(randomx_seed_height(2113) == 2048, "seed rotation boundary");
        require(randomx_seed_height(4160) == 2048 && randomx_seed_height(4161) == 4096, "second rotation");
        require(randomx_seed_height(std::numeric_limits<std::uint64_t>::max()) < std::numeric_limits<std::uint64_t>::max(), "seed overflow boundary");
        Hash zero{}, target{}, low{}, high{};
        target[31] = 1;
        low[0] = 255;
        high[31] = 2;
        require(!meets_target(zero, zero), "zero target rejected");
        require(meets_target(low, target), "little-endian comparison");
        require(meets_target(target, target), "inclusive target");
        require(!meets_target(high, target), "insufficient work rejected");
        require(shielded_status() == ShieldedStatus::backend_unavailable, "no fake privacy backend");
        if (randomx_available()) {
            RandomXHasher hasher(zero);
            const std::uint8_t header[] = {1, 2, 3, 4};
            const auto first = hasher.hash(header);
            require(first == hasher.hash(header), "RandomX deterministic hash");
            const std::uint8_t changed[] = {1, 2, 3, 5};
            require(first != hasher.hash(changed), "RandomX binds header bytes");
            bool rejected = false;
            try { (void)hasher.hash({}); } catch (const std::invalid_argument&) { rejected = true; }
            require(rejected, "empty header rejected");
        } else {
            bool rejected = false;
            try { RandomXHasher unavailable(zero); } catch (const std::runtime_error&) { rejected = true; }
            require(rejected, "no fallback hashing algorithm");
        }
        std::cout << checks << " checks passed\n";
        return 0;
    } catch (const std::exception& e) {
        std::cerr << "FAILED: " << e.what() << '\n';
        return 1;
    }
}
