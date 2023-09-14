from invoke import Collection

from . import k8s

ns = Collection(
    k8s,
)
