from invoke import Collection

from . import qemu
from . import ovmf
from . import svsm
ns = Collection(
    qemu,
    ovmf,
    svsm
)
