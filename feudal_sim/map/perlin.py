"""
Seeded 2D Perlin noise + fBm — replaces the unmaintained `noise` C package,
whose extension modules reference each other's symbols circularly and fail to
load on Linux ("undefined symbol: grad1 / fast_cos").

API-compatible with how hex_grid used noise.pnoise2:
    fbm2(x, y, octaves, persistence, lacunarity, seed)

Deterministic per seed. Output range approximately [-1, 1] like pnoise2
(not bit-identical to the old C library — worldgen character is preserved,
exact tile values are not).
"""

import numpy as np

_PERM_SIZE = 256
_GRADIENTS = np.array(
    [[1, 1], [-1, 1], [1, -1], [-1, -1],
     [1, 0], [-1, 0], [0, 1], [0, -1]],
    dtype=np.float64,
)

_perms: dict = {}


def _permutation(seed: int) -> np.ndarray:
    perm = _perms.get(seed)
    if perm is None:
        rng = np.random.default_rng(seed)
        # Doubled table (classic Perlin trick) so perm[xi + 1] can't overflow
        p = rng.permutation(_PERM_SIZE).astype(np.int64)
        perm = np.concatenate([p, p])
        _perms[seed] = perm
    return perm


def _fade(t: float) -> float:
    return t * t * t * (t * (t * 6 - 15) + 10)


def _lerp(a: float, b: float, t: float) -> float:
    return a + t * (b - a)


def noise2(x: float, y: float, seed: int) -> float:
    """Classic Perlin improved noise at (x, y), deterministic per seed."""
    perm = _permutation(seed)

    xi = int(np.floor(x)) & 255
    yi = int(np.floor(y)) & 255
    xf = x - np.floor(x)
    yf = y - np.floor(y)

    def grad(hash_val: int, dx: float, dy: float) -> float:
        g = _GRADIENTS[hash_val & 7]
        return g[0] * dx + g[1] * dy

    aa = perm[(perm[xi] + yi) & 511]
    ab = perm[(perm[xi] + yi + 1) & 511]
    ba = perm[(perm[xi + 1] + yi) & 511]
    bb = perm[(perm[xi + 1] + yi + 1) & 511]

    u = _fade(xf)
    v = _fade(yf)

    x1 = _lerp(grad(aa, xf, yf), grad(ba, xf - 1, yf), u)
    x2 = _lerp(grad(ab, xf, yf - 1), grad(bb, xf - 1, yf - 1), u)
    return _lerp(x1, x2, v)


def fbm2(
    x: float,
    y: float,
    octaves: int = 4,
    persistence: float = 0.5,
    lacunarity: float = 2.0,
    seed: int = 0,
) -> float:
    """Fractional Brownian motion over Perlin octaves (pnoise2 equivalent)."""
    total = 0.0
    amplitude = 1.0
    frequency = 1.0
    max_amplitude = 0.0
    for _ in range(octaves):
        total += noise2(x * frequency, y * frequency, seed) * amplitude
        max_amplitude += amplitude
        amplitude *= persistence
        frequency *= lacunarity
    return total / max_amplitude if max_amplitude else 0.0
