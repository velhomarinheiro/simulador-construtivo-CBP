"""
Grade hexagonal e terreno do teatro de operações.

Mesma geometria do wargame Operação Atlântico Sul: grade 16x10 em offset
odd-q (hex flat-top), sobre a costa Sudeste do Brasil, cobrindo as bacias
de Campos e Santos.

Terrenos:
    0 T_LAND    — terra (bases, portos, baterias)
    1 T_SHALLOW — águas rasas / costeiras
    2 T_SHELF   — plataforma continental
    3 T_DEEP    — águas profundas
    4 T_OIL     — campos de petróleo (pré-sal)
"""

from __future__ import annotations

GRID_W = 16
GRID_H = 10

T_LAND, T_SHALLOW, T_SHELF, T_DEEP, T_OIL = 0, 1, 2, 3, 4

TERRAIN_NAMES = {
    T_LAND: "Terra",
    T_SHALLOW: "Águas rasas",
    T_SHELF: "Plataforma continental",
    T_DEEP: "Águas profundas",
    T_OIL: "Campos de petróleo",
}

# Espelho de TERRAIN_MAP do wargame-naval (server.js / public/js/terrain.js).
TERRAIN_MAP = [
    [0, 0, 0, 0, 0, 0, 1, 2, 3, 3, 3, 3, 3, 3, 3, 3],
    [0, 0, 0, 0, 0, 1, 1, 2, 3, 3, 3, 3, 3, 3, 3, 3],
    [0, 0, 0, 0, 1, 1, 2, 4, 3, 3, 3, 3, 3, 3, 3, 3],
    [0, 0, 0, 1, 1, 2, 4, 4, 3, 3, 3, 3, 3, 3, 3, 3],
    [0, 0, 1, 1, 2, 4, 4, 2, 3, 3, 3, 3, 3, 3, 3, 3],
    [0, 1, 1, 2, 4, 4, 2, 3, 3, 3, 3, 3, 3, 3, 3, 3],
    [1, 1, 2, 4, 4, 2, 3, 3, 3, 3, 3, 3, 3, 3, 3, 3],
    [1, 2, 2, 4, 2, 2, 3, 3, 3, 3, 3, 3, 3, 3, 3, 3],
    [1, 2, 2, 2, 2, 3, 3, 3, 3, 3, 3, 3, 3, 3, 3, 3],
    [1, 2, 2, 2, 3, 3, 3, 3, 3, 3, 3, 3, 3, 3, 3, 3],
]


def get_terrain(col: int, row: int) -> int:
    if row < 0 or row >= GRID_H or col < 0 or col >= GRID_W:
        return T_LAND
    return TERRAIN_MAP[row][col]


def can_enter_terrain(category: str, terrain: int) -> bool:
    """Regra de ocupação por categoria de unidade (idêntica ao wargame)."""
    if category in ("air", "specops"):
        return True
    if category == "land":
        return terrain in (T_LAND, T_SHALLOW)
    if category == "submarine":
        return terrain not in (T_LAND, T_SHALLOW)
    return terrain != T_LAND  # surface


# ── Matemática hexagonal (odd-q offset, flat-top) ────────────────────────────

def oddq_to_cube(col: int, row: int) -> tuple[int, int, int]:
    x = col
    z = row - (col - (col & 1)) // 2
    return x, -x - z, z


def cube_to_oddq(x: int, z: int) -> tuple[int, int]:
    return x, z + (x - (x & 1)) // 2


_CUBE_DIRS = [(1, -1, 0), (1, 0, -1), (0, 1, -1), (-1, 1, 0), (-1, 0, 1), (0, -1, 1)]


def hex_neighbors(col: int, row: int) -> list[tuple[int, int]]:
    x, _, z = oddq_to_cube(col, row)
    out = []
    for dx, _dy, dz in _CUBE_DIRS:
        nc, nr = cube_to_oddq(x + dx, z + dz)
        if 0 <= nc < GRID_W and 0 <= nr < GRID_H:
            out.append((nc, nr))
    return out


def hex_dist(c1: int, r1: int, c2: int, r2: int) -> int:
    ax, ay, az = oddq_to_cube(c1, r1)
    bx, by, bz = oddq_to_cube(c2, r2)
    return max(abs(ax - bx), abs(ay - by), abs(az - bz))


def hex_label(col: int, row: int) -> str:
    """Rótulo tipo carta náutica: coluna A..P, linha 1..10."""
    return f"{chr(65 + col)}{row + 1}"
