from enum import IntEnum


class Peran(IntEnum):
    WARGA = 1
    RT = 2
    RW = 3
    KEPALA_DESA = 4
    ADMIN = 5


class OTPPurpose(IntEnum):
    LOGIN = 1
    RESET_PASSWORD = 2

