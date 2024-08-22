from invoke import Collection

from . import apps
from . import coco
from . import containerd
from . import cosign
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
from . import sev
from . import skopeo

from tasks.eval import ns as eval_ns

ns = Collection(
    apps,
    coco,
    containerd,
    cosign,
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
    sev,
    skopeo,
)

ns.add_collection(eval_ns, name="eval")
