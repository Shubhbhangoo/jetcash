#include "jetcash/consensus.hpp"
#include "jetcash/pow.hpp"
#include <charconv>
#include <exception>
#include <iomanip>
#include <iostream>
#include <stdexcept>
#include <string_view>

namespace {
std::uint64_t parse_height(std::string_view text) {
    std::uint64_t height{};
    const auto [end, error] = std::from_chars(text.data(), text.data() + text.size(), height);
    if (error != std::errc{} || end != text.data() + text.size())
        throw std::invalid_argument("height must be an unsigned 64-bit integer");
    return height;
}
}
int main(int argc, char** argv) {
    try {
        const std::string_view command = argc > 1 ? argv[1] : "status";
        if (command == "status" && argc <= 2) {
            std::cout << "JetCash policy inspection tool -- full C++ node: jetcashd\n"
                      << "Hard cap: " << jetcash::format_amount(jetcash::max_supply) << " JET\n"
                      << "Draft block target: 60 seconds (not finality)\n"
                      << "RandomX: " << (jetcash::randomx_available() ? "enabled" : "disabled") << '\n'
                      << "Private payments and mainnet: use engine/ and the JetCash wallets\n";
            return 0;
        }
        if (command == "supply" && argc == 3) {
            const auto height = parse_height(argv[2]);
            std::cout << "Height: " << height << "\nIssued: "
                      << jetcash::format_amount(jetcash::issued_supply(height))
                      << " JET\nSubsidy: " << jetcash::format_amount(jetcash::block_subsidy(height))
                      << " JET\n";
            return 0;
        }
        if (command == "pow-demo" && argc == 2) {
            // Demonstration only: the zero seed is not a chain's genesis hash.
            jetcash::RandomXHasher hasher(jetcash::Hash{});
            constexpr std::string_view input = "JetCash research header v1";
            const auto hash = hasher.hash({reinterpret_cast<const std::uint8_t*>(input.data()), input.size()});
            std::cout << "RandomX demo (not a mined block): ";
            for (const auto b : hash) std::cout << std::hex << std::setw(2) << std::setfill('0') << unsigned(b);
            std::cout << '\n';
            return 0;
        }
        std::cerr << "Usage: jetcash-policy [status | supply HEIGHT | pow-demo]\n";
        return 2;
    } catch (const std::exception& e) {
        std::cerr << "Error: " << e.what() << '\n';
        return 1;
    }
}
