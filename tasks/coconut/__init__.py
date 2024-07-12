from invoke import Collection

from . import qemu
from . import ovmf
from . import svsm
from . import guest_kernel
ns = Collection(
    qemu,
    ovmf,
    svsm,
    guest_kernel,
)
