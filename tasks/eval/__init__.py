from invoke import Collection

from . import mem_size
from . import startup
from . import vm_detail
from . import xput

ns = Collection(
    mem_size,
    startup,
    vm_detail,
    xput,
)
