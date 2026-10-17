// libtorrent 1.2.20's RC4 (src/pe_crypto.cpp, byte-at-a-time) vs OpenSSL RC4().
#define OPENSSL_SUPPRESS_DEPRECATED
#include <openssl/rc4.h>
#include <chrono>
#include <cstdint>
#include <cstdio>
#include <cstring>
#include <vector>

struct lt_rc4 { int x, y; std::uint8_t buf[256]; };

static void lt_rc4_init(const unsigned char* in, std::size_t len, lt_rc4* state) {  // verbatim logic
    std::size_t const key_size = sizeof(state->buf);
    std::uint8_t key[key_size];
    std::uint8_t* s = state->buf;
    std::memcpy(key, in, len);
    state->x = 0; state->y = 0;
    for (std::size_t x = 0; x < key_size; ++x) s[x] = std::uint8_t(x);
    for (std::size_t j = 0, x = 0; x < key_size; ++x) {
        j = (j + s[x] + key[x % len]) & 255;
        std::uint8_t tmp = s[x]; s[x] = s[j]; s[j] = tmp;
    }
}

static void lt_rc4_encrypt(unsigned char* out, std::size_t outlen, lt_rc4* state) {  // verbatim loop
    std::uint8_t x = state->x & 0xff, y = state->y & 0xff, *s = state->buf, tmp;
    while (outlen--) {
        x = (x + 1) & 255;
        y = (y + s[x]) & 255;
        tmp = s[x]; s[x] = s[y]; s[y] = tmp;
        tmp = (s[x] + s[y]) & 255;
        *out++ ^= s[tmp];
    }
    state->x = x; state->y = y;
}

int main() {
    const std::size_t n = 256u << 20;
    std::vector<unsigned char> a(n, 0x5a), b(n, 0x5a);
    unsigned char key[20]; for (int i = 0; i < 20; ++i) key[i] = (unsigned char)(i * 7 + 3);

    lt_rc4 st; lt_rc4_init(key, 20, &st);
    auto t0 = std::chrono::steady_clock::now();
    for (std::size_t off = 0; off < n; off += 16384) lt_rc4_encrypt(a.data() + off, 16384, &st);  // per 16 KiB block
    double lt_s = std::chrono::duration<double>(std::chrono::steady_clock::now() - t0).count();

    RC4_KEY k; RC4_set_key(&k, 20, key);
    t0 = std::chrono::steady_clock::now();
    for (std::size_t off = 0; off < n; off += 16384) RC4(&k, 16384, b.data() + off, b.data() + off);
    double ossl_s = std::chrono::duration<double>(std::chrono::steady_clock::now() - t0).count();

    std::printf("identical keystream output: %s\n", std::memcmp(a.data(), b.data(), n) == 0 ? "yes" : "NO");
    std::printf("libtorrent RC4 loop : %7.2f GB/s per core\n", n / lt_s / 1e9);
    std::printf("OpenSSL RC4()       : %7.2f GB/s per core  (%.1fx)\n", n / ossl_s / 1e9, lt_s / ossl_s);
}
