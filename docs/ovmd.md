## OVMF

To enable OVMF logging, we neeed to re-build OVMF from source with the `DEBUG`
target.

To do so, you may run:

```bash
inv ovmf.set-log-level debug
```

which will build OVMF from source, and configure Kata to use our version of
OVMF.

You may directly re-build OVMF by running:

```bash
inv ovmf.build [--target DEBUG,RELEASE]
```
