from invoke import Collection

from . import kubeadm
from . import uk8s

ns = Collection(
    kubeadm,
    uk8s,
)
