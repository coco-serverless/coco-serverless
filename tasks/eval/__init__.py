from invoke import Collection

from . import image_pull
from . import images
from . import initrd_size
from . import mem_size
from . import ovmf_detail
from . import prune
from . import startup
from . import vm_detail
from . import xput
from . import xput_detail

ns = Collection(
    image_pull,
    images,
    initrd_size,
    mem_size,
    ovmf_detail,
    prune,
    startup,
    vm_detail,
    xput,
    xput_detail,
)
