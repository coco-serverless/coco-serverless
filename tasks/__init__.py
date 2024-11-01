from invoke import Collection

from . import coco
from . import containerd
from . import cosign
from . import demo_apps
from . import format_code
from . import gc
from . import k8s
from . import k9s
from . import kata
from . import kbs
from . import knative
from . import kubeadm
from . import nydus
from . import operator
from . import ovmf
from . import qemu
from . import registry
from . import sc2
from . import sev
from . import skopeo

from tasks.coconut import ns as coconut_ns

ns = Collection(
    coco,
    containerd,
    cosign,
    demo_apps,
    format_code,
    gc,
    k8s,
    k9s,
    kata,
    kbs,
    knative,
    kubeadm,
    nydus,
    operator,
    ovmf,
    qemu,
    registry,
    sc2,
    sev,
    skopeo,
)

ns.add_collection(coconut_ns, name="coconut")
