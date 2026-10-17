// DH handshake cost as done by libtorrent MSE/PE: 768-bit prime, generator 2,
// two modexps per handshake (local key + shared secret).
#include <boost/multiprecision/cpp_int.hpp>
#include <openssl/bn.h>
#include <openssl/rand.h>
#include <chrono>
#include <cstdio>
#include <vector>

namespace mp = boost::multiprecision;
using dh_int = mp::number<mp::cpp_int_backend<768, 768, mp::unsigned_magnitude, mp::unchecked, void>>;

static const unsigned char prime_bytes[96] = {  // same prime as libtorrent pe_crypto.cpp
    0xFF,0xFF,0xFF,0xFF,0xFF,0xFF,0xFF,0xFF,0xC9,0x0F,0xDA,0xA2,0x21,0x68,0xC2,0x34,0xC4,0xC6,0x62,0x8B,0x80,0xDC,0x1C,0xD1,
    0x29,0x02,0x4E,0x08,0x8A,0x67,0xCC,0x74,0x02,0x0B,0xBE,0xA6,0x3B,0x13,0x9B,0x22,0x51,0x4A,0x08,0x79,0x8E,0x34,0x04,0xDD,
    0xEF,0x95,0x19,0xB3,0xCD,0x3A,0x43,0x1B,0x30,0x2B,0x0A,0x6D,0xF2,0x5F,0x14,0x37,0x4F,0xE1,0x35,0x6D,0x6D,0x51,0xC2,0x45,
    0xE4,0x85,0xB5,0x76,0x62,0x5E,0x7E,0xC6,0xF4,0x4C,0x42,0xE9,0xA6,0x3A,0x36,0x20,0xFF,0xFF,0xFF,0xFF,0xFF,0xFF,0xFF,0xFF};

static double boost_handshake_us(int secret_bytes, int n) {
    dh_int p; mp::import_bits(p, prime_bytes, prime_bytes + 96);
    std::vector<unsigned char> r(secret_bytes);
    auto t0 = std::chrono::steady_clock::now();
    dh_int sink = 0;
    for (int i = 0; i < n; ++i) {
        RAND_bytes(r.data(), secret_bytes);
        dh_int secret; mp::import_bits(secret, r.begin(), r.end());
        dh_int local = mp::powm(dh_int(2), secret, p);          // local public key
        dh_int shared = mp::powm(local + 12345, secret, p);    // shared secret (remote key stand-in)
        sink ^= shared;
    }
    auto us = std::chrono::duration<double, std::micro>(std::chrono::steady_clock::now() - t0).count() / n;
    if (sink == 1) std::puts("");
    return us;
}

static double openssl_handshake_us(int secret_bytes, int n) {
    BN_CTX* ctx = BN_CTX_new();
    BIGNUM* p = BN_bin2bn(prime_bytes, 96, nullptr);
    BIGNUM *g = BN_new(), *secret = BN_new(), *local = BN_new(), *shared = BN_new();
    BN_set_word(g, 2);
    BN_MONT_CTX* mont = BN_MONT_CTX_new(); BN_MONT_CTX_set(mont, p, ctx);
    std::vector<unsigned char> r(secret_bytes);
    auto t0 = std::chrono::steady_clock::now();
    for (int i = 0; i < n; ++i) {
        RAND_bytes(r.data(), secret_bytes);
        BN_bin2bn(r.data(), secret_bytes, secret);
        BN_mod_exp_mont(local, g, secret, p, ctx, mont);
        BN_add_word(local, 12345);
        BN_mod_exp_mont(shared, local, secret, p, ctx, mont);
    }
    auto us = std::chrono::duration<double, std::micro>(std::chrono::steady_clock::now() - t0).count() / n;
    BN_MONT_CTX_free(mont); BN_free(g); BN_free(secret); BN_free(local); BN_free(shared); BN_free(p); BN_CTX_free(ctx);
    return us;
}

int main() {
    const int n = 3000;
    double b768 = boost_handshake_us(96, n), b160 = boost_handshake_us(20, n);
    double o768 = openssl_handshake_us(96, n), o160 = openssl_handshake_us(20, n);
    std::printf("per handshake (2 modexps), %d iterations:\n", n);
    std::printf("  boost::multiprecision, 768-bit exponent (libtorrent 1.2.20 today): %8.1f us\n", b768);
    std::printf("  boost::multiprecision, 160-bit exponent (+ PR #8565)             : %8.1f us\n", b160);
    std::printf("  OpenSSL BN_mod_exp_mont, 768-bit exponent                        : %8.1f us\n", o768);
    std::printf("  OpenSSL BN_mod_exp_mont, 160-bit exponent (+ #8565 + #8660)      : %8.1f us\n", o160);
    std::printf("network-thread time for a 500-connection race start: today %.0f ms, #8565 %.0f ms, both %.0f ms\n",
                b768 * 500 / 1000, b160 * 500 / 1000, o160 * 500 / 1000);
}
