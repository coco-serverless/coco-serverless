from invoke import Collection

from . import qemu
from . import ovmf
ns = Collection(
    qemu,
    ovmf,
)
