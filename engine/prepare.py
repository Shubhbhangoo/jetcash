#!/usr/bin/env python3
"""Apply reviewable, idempotent JetCash changes to exactly the pinned source."""
import argparse
import difflib
import hashlib
import json
from pathlib import Path
import re
import subprocess

ROOT = Path(__file__).resolve().parents[1]
PIN = json.loads((ROOT / "engine/upstream.json").read_text())

def replace(text, old, new, count=1):
    actual = text.count(old)
    if actual != count:
        raise RuntimeError(f"upstream context mismatch ({actual} != {count}): {old[:100]}")
    return text.replace(old, new)

def body(text, signature, replacement):
    start = text.index(signature)
    opening = text.index("{", start + len(signature))
    depth = 1
    end = opening + 1
    while depth:
        depth += (text[end] == "{") - (text[end] == "}")
        end += 1
    return text[:opening] + "{\n" + replacement + "\n  }" + text[end:]

def prepare(source):
    source = source.resolve()
    head = subprocess.check_output(["git", "-C", str(source), "rev-parse", "HEAD"], text=True).strip()
    if head != PIN["commit"]:
        raise RuntimeError("refusing to patch a different upstream revision")
    changes = {}
    originals = {}
    manifest_path = source / ".jetcash-overlay.json"
    manifest = json.loads(manifest_path.read_text()) if manifest_path.exists() else {}
    def load(path):
        text = subprocess.check_output(["git", "-C", str(source), "show", f"HEAD:{path}"], text=True)
        originals[path] = text
        return text
    def save(path, text):
        changes[path] = text

    p = "src/cryptonote_config.h"
    t = load(p)
    t = replace(t, '#define MONEY_SUPPLY                                    ((uint64_t)(-1))',
                '#define MONEY_SUPPLY                                    UINT64_C(1000000000000000)')
    t = replace(t, '#define FINAL_SUBSIDY_PER_MINUTE                        ((uint64_t)300000000000)',
                '#define FINAL_SUBSIDY_PER_MINUTE                        UINT64_C(0)')
    t = replace(t, '#define CRYPTONOTE_DISPLAY_DECIMAL_POINT                12',
                '#define CRYPTONOTE_DISPLAY_DECIMAL_POINT                8')
    t = replace(t, '#define COIN                                            ((uint64_t)1000000000000)',
                '#define COIN                                            UINT64_C(100000000)')
    t = replace(t, '#define DIFFICULTY_TARGET_V2                            120',
                '#define DIFFICULTY_TARGET_V2                            60')
    t = replace(t, '#define CRYPTONOTE_NAME                         "bitmonero"',
                '#define CRYPTONOTE_NAME                         "jetcash-dev"')
    # Scale atomic fee constants to the new 8-decimal denomination.
    for name in ["FEE_PER_KB_OLD", "FEE_PER_KB", "FEE_PER_BYTE", "DYNAMIC_FEE_PER_KB_BASE_FEE",
                 "DYNAMIC_FEE_PER_KB_BASE_BLOCK_REWARD", "DYNAMIC_FEE_PER_KB_BASE_FEE_V5"]:
        pattern = rf'(#define {name}\s+\(\(uint64_t\))(\d+)'
        t, count = re.subn(pattern, lambda m: m[1] + str(int(m[2]) // 10000), t)
        if count != 1:
            raise RuntimeError(f"missing fee constant {name}")
    t = replace(t, 'DEFAULT_DUST_THRESHOLD = ((uint64_t)2000000000)', 'DEFAULT_DUST_THRESHOLD = ((uint64_t)200000)')
    t = replace(t, 'BASE_REWARD_CLAMP_THRESHOLD = ((uint64_t)100000000)', 'BASE_REWARD_CLAMP_THRESHOLD = ((uint64_t)10000)')
    prefixes = [(18, 199), (19, 200), (42, 201), (53, 209), (54, 210), (63, 211), (24, 219), (25, 220), (36, 221)]
    for old, new in prefixes:
        t, count = re.subn(rf'(BASE58_PREFIX = ){old};', rf'\g<1>{new};', t)
        if count != 1: raise RuntimeError("address prefix mismatch")
    for old, new in [(18080,41080),(18081,41081),(18082,41082),(28080,42080),(28081,42081),(28082,42082),(38080,43080),(38081,43081),(38082,43082)]:
        t = replace(t, f'= {old};', f'= {new};')
    t = replace(t, '0x12 ,0x30, 0xF1, 0x71 , 0x61, 0x04 , 0x41, 0x61, 0x17, 0x31, 0x00, 0x82, 0x16, 0xA1, 0xA1,',
                '0x4a, 0x45, 0x54, 0x43, 0x41, 0x53, 0x48, 0x44, 0x45, 0x56, 0x30, 0x31, 0x8d, 0x92, 0xb7,', count=3)
    # Canonical v1 genesis transaction with no outputs or initial distribution.
    t, count = re.subn(r'013c01ff0001ffffffffffff0302[0-9a-f]{64}21', '013c01ff000021', t)
    if count != 3: raise RuntimeError("genesis serialization mismatch")
    for old, new in [(10000,41000),(10001,42000),(10002,43000)]:
        t = replace(t, f'GENESIS_NONCE = {old};', f'GENESIS_NONCE = {new};')
    save(p, t)

    p = "src/cryptonote_basic/cryptonote_basic_impl.h"
    t = load(p)
    t = replace(t, 'uint64_t &reward, uint8_t version);', 'uint64_t &reward, uint8_t version, uint64_t height);')
    save(p, t)
    p = "src/cryptonote_basic/cryptonote_basic_impl.cpp"
    t = load(p)
    t = '#include "jetcash_emission.hpp"\n' + t
    t = replace(t, 'uint64_t &reward, uint8_t version) {', 'uint64_t &reward, uint8_t version, uint64_t height) {')
    start = t.index('    static_assert(DIFFICULTY_TARGET_V2')
    end = t.index('    uint64_t full_reward_zone', start)
    t = t[:start] + '''    static_assert(MONEY_SUPPLY == jetcash_policy::cap, "supply constants diverged");
    static_assert(COIN == jetcash_policy::coin, "denomination constants diverged");
    if (already_generated_coins > MONEY_SUPPLY) return false;
    uint64_t base_reward = std::min(jetcash_policy::subsidy(height), MONEY_SUPPLY - already_generated_coins);

''' + t[end:]
    # At zero emission a weight-penalized reward is also zero.
    t = replace(t, 'assert(reward_lo < base_reward);', 'assert(base_reward == 0 ? reward_lo == 0 : reward_lo < base_reward);')
    save(p, t)
    p = "src/cryptonote_core/cryptonote_tx_utils.cpp"
    t = replace(load(p), 'block_reward, hard_fork_version))', 'block_reward, hard_fork_version, height))')
    save(p, t)
    p = "src/cryptonote_core/tx_pool.cpp"
    t = load(p)
    t = replace(t, 'best_coinbase, version))', 'best_coinbase, version, m_blockchain.get_current_blockchain_height()))')
    t = replace(t, 'block_reward, version))', 'block_reward, version, m_blockchain.get_current_blockchain_height()))')
    save(p, t)
    p = "src/cryptonote_core/blockchain.cpp"
    t = load(p)
    t = replace(t, '#define BLOCK_REWARD_OVERESTIMATE (10 * 1000000000000)', '#define BLOCK_REWARD_OVERESTIMATE (10 * COIN)')
    t = replace(t, 'cumulative_block_weight, already_generated_coins, base_reward, version))',
                'cumulative_block_weight, already_generated_coins, base_reward, version, boost::get<txin_gen>(b.miner_tx.vin[0]).height))')
    t = replace(t, 'get_block_reward(median, 1, already_generated_coins, base_reward, version))',
                'get_block_reward(median, 1, already_generated_coins, base_reward, version, blockchain_height))')
    t = replace(t, 'get_block_reward(m_current_block_cumul_weight_limit / 2, 1, already_generated_coins, base_reward, version))',
                'get_block_reward(m_current_block_cumul_weight_limit / 2, 1, already_generated_coins, base_reward, version, db_height))', count=2)
    # Check addition before comparing rewards; don't rely on a wrapping sum.
    t = replace(t, '  if(base_reward + fee < money_in_use)',
                '  if (fee > MONEY_SUPPLY || base_reward > MONEY_SUPPLY - fee) return false;\n  if(base_reward + fee < money_in_use)')
    # Retain a nonzero admission fee when the block subsidy ends.
    t = replace(t, 'const uint64_t Fl = base_reward * /*Brlw*/ DYNAMIC_FEE_REFERENCE_TRANSACTION_WEIGHT / (Mfw * Mfw);',
                'const uint64_t Fl = std::max<uint64_t>(1, base_reward * DYNAMIC_FEE_REFERENCE_TRANSACTION_WEIGHT / (Mfw * Mfw));')
    t = replace(t, 'const uint64_t Fn = 4 * base_reward * /*Brlw*/ DYNAMIC_FEE_REFERENCE_TRANSACTION_WEIGHT / (Mfw * Mfw);',
                'const uint64_t Fn = std::max<uint64_t>(4, 4 * base_reward * DYNAMIC_FEE_REFERENCE_TRANSACTION_WEIGHT / (Mfw * Mfw));')
    t = replace(t, 'const uint64_t Fm = 16 * base_reward * DYNAMIC_FEE_REFERENCE_TRANSACTION_WEIGHT / (CRYPTONOTE_BLOCK_GRANTED_FULL_REWARD_ZONE_V5 * Mfw);',
                'const uint64_t Fm = std::max<uint64_t>(16, 16 * base_reward * DYNAMIC_FEE_REFERENCE_TRANSACTION_WEIGHT / (CRYPTONOTE_BLOCK_GRANTED_FULL_REWARD_ZONE_V5 * Mfw));')
    save(p, t)

    p = "src/hardforks/hardforks.cpp"
    t = load(p)
    for network in ["mainnet", "testnet", "stagenet"]:
        t, count = re.subn(rf'(const hardfork_t {network}_hard_forks\[\] = )\{{.*?\n\}};',
                          r'\1{\n  { 1, 0, 0, 0 },\n  { 16, 1, 0, 1 },\n};', t, flags=re.S)
        if count != 1: raise RuntimeError("fork schedule mismatch")
        t = re.sub(rf'({network}_hard_fork_version_1_till = )\d+;', r'\g<1>0;', t)
    save(p, t)
    p = "src/checkpoints/checkpoints.cpp"
    t = load(p)
    for function in ["init_default_checkpoints", "load_checkpoints_from_dns"]:
        t = body(t, f'bool checkpoints::{function}(network_type nettype)', '    (void)nettype;\n    return true; // JetCash has no upstream checkpoints.')
    save(p, t)
    p = "src/p2p/net_node.inl"
    t = load(p)
    t = body(t, 'node_server<t_payload_net_handler>::get_ip_seed_nodes() const', '    return {}; // Explicit JetCash peers only.')
    t = body(t, 'node_server<t_payload_net_handler>::get_dns_seed_nodes()', '    return {};')
    t = body(t, 'node_server<t_payload_net_handler>::get_seed_nodes(epee::net_utils::zone zone)', '    (void)zone;\n    return {};')
    t = body(t, 'node_server<t_payload_net_handler>::update_dns_blocklist()', '    return true; // Upstream blocklists are not JetCash authority.')
    t = replace(t, '      memcpy(&m_network_id, &::config::NETWORK_ID, 16);',
                '      memcpy(&m_network_id, &::config::NETWORK_ID, 16);\n'
                '      if (m_nettype == cryptonote::FAKECHAIN) m_network_id.data[15] = 0x7f;')
    save(p, t)
    p = "CMakeLists.txt"
    t = replace(load(p), 'set(PER_BLOCK_CHECKPOINT 1)', 'set(PER_BLOCK_CHECKPOINT 0)')
    save(p, t)
    p = "src/cryptonote_core/cryptonote_core.cpp"
    t = load(p)
    # Restore the upstream selector: no network flag selects JetCash MAINNET.
    # Synthetic difficulty is allowed only on the isolated regression profile.
    t = replace(t, '    const difficulty_type fixed_difficulty = command_line::get_arg(vm, arg_fixed_difficulty);',
                '    const difficulty_type fixed_difficulty = command_line::get_arg(vm, arg_fixed_difficulty);\n'
                '    CHECK_AND_ASSERT_MES(m_nettype == FAKECHAIN || fixed_difficulty == 0, false, "Fixed difficulty is restricted to --regtest");')
    save(p, t)
    for p, old, new in [("src/daemon/CMakeLists.txt", 'OUTPUT_NAME "monerod"', 'OUTPUT_NAME "jetcashd"'),
                        ("src/wallet/CMakeLists.txt", 'OUTPUT_NAME "monero-wallet-rpc"', 'OUTPUT_NAME "jetcash-wallet-rpc"'),
                        ("src/simplewallet/CMakeLists.txt", 'OUTPUT_NAME "monero-wallet-cli"', 'OUTPUT_NAME "jetcash-wallet-cli"')]:
        save(p, replace(load(p), old, new))
    p = "src/version.cpp.in"
    t = replace(load(p), '#define DEF_MONERO_VERSION "0.18.5.3"', '#define DEF_MONERO_VERSION "0.1.0-jetcash-dev-monero-0.18.5.3"')
    save(p, t)
    # Disable upstream update authority in daemon, CLI/RPC, and wallet API paths.
    p = "src/common/updates.cpp"
    t = load(p)
    signature = t[t.index('  bool check_updates('):]
    signature = signature[:signature.index('{')].strip()
    t = body(t, signature, '    return false; // JetCash never downloads Monero updates.')
    save(p, t)
    p = "src/daemon/main.cpp"
    t = replace(load(p), 'catch (const std::runtime_error&)', 'catch (const std::runtime_error& error)')
    t, count = re.subn(r'std::cerr << "Can.t specify more than one of --tesnet and --stagenet and --regtest"',
                      'std::cerr << error.what()', t)
    if count != 1: raise RuntimeError("startup exception handler mismatch")
    t = t.replace('"Monero ', '"JetCash dev (Monero-derived) ')
    save(p, t)
    p = "src/wallet/wallet2.cpp"
    t = load(p)
    signature = 'void check_block_hard_fork_version(cryptonote::network_type nettype, uint8_t hf_version, uint64_t height, bool &wallet_is_outdated, bool &daemon_is_outdated)'
    t = body(t, signature, '''  const size_t count = nettype == TESTNET ? num_testnet_hard_forks
    : nettype == STAGENET ? num_stagenet_hard_forks : num_mainnet_hard_forks;
  const hardfork_t *forks = nettype == TESTNET ? testnet_hard_forks
    : nettype == STAGENET ? stagenet_hard_forks : mainnet_hard_forks;
  wallet_is_outdated = hf_version > forks[count - 1].version;
  daemon_is_outdated = false;
  if (wallet_is_outdated) return;
  uint8_t expected = forks[0].version;
  for (size_t i = 1; i < count && forks[i].height <= height; ++i)
    expected = forks[i].version;
  daemon_is_outdated = hf_version != expected;''')
    t = replace(t, 'get_hard_fork_info(wallet_num_hard_forks-1/* wallet expects "double fork" pattern */, daemon_fork_height);',
                'get_hard_fork_info(wallet_hard_forks[wallet_num_hard_forks - 1].version, daemon_fork_height);')
    t = replace(t, '  if (daemon_hard_forks.size() > 0)\n  {', '''  if (daemon_hard_forks.size() > 0)
  {
    for (size_t i = 0; i < std::min(daemon_hard_forks.size(), wallet_num_hard_forks); ++i)
    {
      if (daemon_hard_forks[i].first != wallet_hard_forks[i].version ||
          daemon_hard_forks[i].second != wallet_hard_forks[i].height)
      {
        if (daemon_is_outdated) *daemon_is_outdated = true;
        if (wallet_is_outdated) *wallet_is_outdated = false;
        return false;
      }
    }''')
    save(p, t)

    p = "src/cryptonote_basic/cryptonote_format_utils.cpp"
    t = load(p)
    t = body(t, 'void set_default_decimal_point(unsigned int decimal_point)', '''    if (decimal_point != 8 && decimal_point != 5 && decimal_point != 2 && decimal_point != 0)
      ASSERT_MES_AND_THROW("Invalid JetCash decimal point specification: " << decimal_point);
    default_decimal_point = decimal_point;''')
    t = body(t, 'std::string get_unit(unsigned int decimal_point)', '''    if (decimal_point == (unsigned int)-1) decimal_point = default_decimal_point;
    switch (decimal_point) {
      case 8: return "JET";
      case 5: return "mJET";
      case 2: return "uJET";
      case 0: return "atomic";
      default: ASSERT_MES_AND_THROW("Invalid JetCash decimal point specification: " << decimal_point);
    }''')
    save(p, t)
    p = "src/simplewallet/simplewallet.cpp"
    t = load(p)
    t = replace(t, '  else if (unit == "nanonero")\n    decimal_point = CRYPTONOTE_DISPLAY_DECIMAL_POINT - 9;\n', '')
    for old, new in [('unit == "monero"', 'unit == "JET"'), ('unit == "millinero"', 'unit == "mJET"'),
                     ('unit == "micronero"', 'unit == "uJET"'), ('unit == "piconero"', 'unit == "atomic"'),
                     ('unit <monero|millinero|micronero|nanonero|piconero>', 'unit <JET|mJET|uJET|atomic>')]:
        t = replace(t, old, new)
    t = t.replace(' XMR', ' JET')
    save(p, t)

    # The test links the actual engine reward implementation, not a duplicate model.
    changes["CMakeLists.txt"] += '''
add_executable(jetcash-consensus-tests src/jetcash_reward_tests.cpp)
target_link_libraries(jetcash-consensus-tests PRIVATE wallet)
'''
    # Stage all checks first. Refuse to overwrite edits not produced by this overlay.
    for p, desired in changes.items():
        current = (source / p).read_text()
        if current not in (originals[p], desired) and hashlib.sha256(current.encode()).hexdigest() != manifest.get(p):
            raise RuntimeError(f"unrecognized local edits in {source / p}")
    for p, desired in changes.items():
        if (source / p).read_text() != desired:
            (source / p).write_text(desired)
    for destination, origin in [("src/jetcash_emission.hpp", "include/jetcash/emission.hpp"),
                                ("src/jetcash_reward_tests.cpp", "engine/reward_tests.cpp")]:
        data = (ROOT / origin).read_bytes()
        target = source / destination
        if not target.exists() or target.read_bytes() != data:
            target.write_bytes(data)
    manifest_path.write_text(json.dumps({p: hashlib.sha256(t.encode()).hexdigest() for p, t in changes.items()}, indent=2))
    diff = subprocess.check_output(["git", "-C", str(source), "diff", "HEAD", "--", *sorted(changes)], text=True)
    for destination in ["src/jetcash_emission.hpp", "src/jetcash_reward_tests.cpp"]:
        diff += "".join(difflib.unified_diff([], (source / destination).read_text().splitlines(keepends=True),
                                          fromfile="/dev/null", tofile="b/" + destination))
    (ROOT / "engine/jetcash.patch").write_text(diff)
    print(f"JetCash overlay applied to {source}: {len(changes)} upstream files")

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("source", type=Path)
    args = parser.parse_args()
    prepare(args.source)
