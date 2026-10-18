#define _GNU_SOURCE
#include <dlfcn.h>
#include <errno.h>
#include <stdint.h>
#include <sys/mman.h>
#include <unistd.h>

#ifndef MAP_FIXED_NOREPLACE
#define MAP_FIXED_NOREPLACE 0x100000
#endif

typedef void *(*mmap_fn)(void *, size_t, int, int, int, off_t);

static void *map_low(mmap_fn real, void *addr, size_t len, int prot, int flags,
                     int fd, off_t off) {
    const uint64_t limit = 1ULL << 32;
    const uint64_t step = 1ULL << 20;
    int low_flags = (flags & ~MAP_32BIT) | MAP_FIXED_NOREPLACE;
    for (uint64_t hint = 0x10000000ULL; hint + len <= limit; hint += step) {
        void *p = real((void *)hint, len, prot, low_flags, fd, off);
        if (p != MAP_FAILED) {
            if ((uint64_t)p == hint) return p;
            munmap(p, len);
        }
    }
    errno = ENOMEM;
    return MAP_FAILED;
}

void *mmap(void *addr, size_t len, int prot, int flags, int fd, off_t off) {
    static mmap_fn real;
    if (!real) real = (mmap_fn)dlsym(RTLD_NEXT, "mmap");
    if (flags & MAP_32BIT) return map_low(real, addr, len, prot, flags, fd, off);
    return real(addr, len, prot, flags, fd, off);
}

void *mmap64(void *addr, size_t len, int prot, int flags, int fd, off_t off) {
    return mmap(addr, len, prot, flags, fd, off);
}
