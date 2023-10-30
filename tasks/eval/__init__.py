from invoke import Collection

from . import image_pull
from . import mem_size
from . import startup
from . import vm_detail
from . import xput

ns = Collection(
    image_pull,
    mem_size,
    startup,
    vm_detail,
    xput,
)
