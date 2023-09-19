from invoke import Collection

from . import apps
from . import containerd
from . import format_code
from . import kubeadm
from . import k8s
from . import k9s
from . import operator
from . import uk8s

ns = Collection(
    apps,
    containerd,
    format_code,
    kubeadm,
    k8s,
    k9s,
    operator,
    uk8s,
)
