from invoke import Collection

from . import format_code
from . import kubeadm
from . import uk8s

ns = Collection(
    format_code,
    kubeadm,
    uk8s,
)
