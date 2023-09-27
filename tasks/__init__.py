from invoke import Collection

from . import apps
from . import containerd
from . import format_code
from . import k8s
from . import k9s
from . import kata
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
    kata,
    kbs,
    knative,
    kubeadm,
    operator,
)
