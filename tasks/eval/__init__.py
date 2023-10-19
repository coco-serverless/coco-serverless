from invoke import Collection

from . import mem_size
from . import startup
from . import xput

ns = Collection(
    mem_size,
    startup,
    xput,
)
