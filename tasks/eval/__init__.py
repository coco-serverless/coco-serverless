from invoke import Collection

from . import startup
from . import xput

ns = Collection(
    startup,
    xput,
)
