from invoke import Collection

from . import apps
from . import containerd
from . import format_code
from . import k8s
from . import k9s
from . import kbs
from . import knative
from . import kubeadm
from . import operator

ns = Collection(
    apps,
    containerd,
    format_code,
    k8s,
    k9s,
    kbs,
    knative,
    kubeadm,
    operator,
)
