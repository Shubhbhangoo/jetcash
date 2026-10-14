#include "cryptonote_basic/cryptonote_basic_impl.h"
#include "cryptonote_basic/cryptonote_format_utils.h"
#include "cryptonote_config.h"
#include "jetcash_emission.hpp"
#include <iostream>
#include <limits>
#include <stdexcept>

namespace tools {
void check_block_hard_fork_version(cryptonote::network_type, uint8_t, uint64_t, bool&, bool&);
}

int main() {
    unsigned checks = 0;
    auto require = [&](bool result) {
        ++checks;
        if (!result) throw std::runtime_error("engine reward check " + std::to_string(checks));
    };
    try {
        using namespace jetcash_policy;
        uint64_t reward = 0;
        for (uint64_t era = 0; era < eras; ++era) {
            for (const uint64_t height : {era * interval + 1, (era + 1) * interval}) {
                require(cryptonote::get_block_reward(300000, 1000, issued(height - 1), reward, 16, height));
                require(reward == subsidy(height));
            }
        }
        require(cryptonote::get_block_reward(300000, 1000, 0, reward, 1, 0) && reward == 0);
        require(cryptonote::get_block_reward(300000, 1000, issued(last_height - 1), reward, 16, last_height));
        require(reward == 13'000'000);
        require(cryptonote::get_block_reward(300000, 1000, cap, reward, 16, last_height + 1) && reward == 0);
        require(!cryptonote::get_block_reward(300000, 1000, cap + 1, reward, 16, 1));
        require(!cryptonote::get_block_reward(300000, 1000, UINT64_MAX, reward, 16, 1));
        require(cryptonote::get_block_reward(300000, 1000, cap - 1, reward, 16, 1) && reward == 1);
        require(cryptonote::get_block_reward(300000, 450000, 0, reward, 16, 1) && reward < subsidy(1));
        require(!cryptonote::get_block_reward(300000, 600001, 0, reward, 16, 1));
        require(cryptonote::get_block_reward(300000, 450000, cap, reward, 16, last_height + 1) && reward == 0);
        for (const auto point : {8u, 5u, 2u, 0u}) {
            cryptonote::set_default_decimal_point(point);
            require(!cryptonote::get_unit().empty());
        }
        cryptonote::set_default_decimal_point(8);
        require(cryptonote::get_unit() == "JET");
        require(cryptonote::print_money(coin) == "1.00000000");
        for (const auto network : {cryptonote::MAINNET, cryptonote::TESTNET, cryptonote::STAGENET}) {
            bool wallet_old, daemon_old;
            tools::check_block_hard_fork_version(network, 1, 0, wallet_old, daemon_old);
            require(!wallet_old && !daemon_old);
            tools::check_block_hard_fork_version(network, 16, 1, wallet_old, daemon_old);
            require(!wallet_old && !daemon_old);
            tools::check_block_hard_fork_version(network, 1, 1, wallet_old, daemon_old);
            require(!wallet_old && daemon_old);
            tools::check_block_hard_fork_version(network, 2, 1, wallet_old, daemon_old);
            require(!wallet_old && daemon_old);
            tools::check_block_hard_fork_version(network, 17, 1, wallet_old, daemon_old);
            require(wallet_old);
            tools::check_block_hard_fork_version(network, 16, 0, wallet_old, daemon_old);
            require(!wallet_old && daemon_old);
        }
        std::cout << checks << " actual daemon consensus checks passed\n";
    } catch (const std::exception& e) {
        std::cerr << e.what() << '\n';
        return 1;
    }
}
