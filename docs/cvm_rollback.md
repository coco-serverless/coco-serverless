# cVM Rollback

## Experiments 

### Communicate with the SVSM

To communicate between the Secure VM Service Module (SVSM) and the guest, we can define and use our own protocol. Refer to Section 5 of AMD's [Secure VM Service Module for SEV-SNP Guests](https://www.amd.com/content/dam/amd/en/documents/epyc-technical-docs/specifications/58019.pdf) documentation for more details.

On the guest side, are using a new system call to invoke the protocol from the guest user space (see [GitHub coco-serverless Linux fork](https://github.com/coco-serverless/linux/blob/svsm/arch/x86/entry/syscalls/syscall_64.tbl#L432)). 

```C
syscall(svsm, REQUEST_NUMBER);
```

The guest kernel then executes the protocol call.

On the SVSM side, requests to our new protocol are handled by `request_loop_once` in `svsm/kernel/src/requests.rs` (see [GitHub coco-serverless SVSM fork](https://github.com/coco-serverless/svsm/blob/main/kernel/src/requests.rs#L115)).



### Restore the memory of the guest to a well-known state

In serverless computing, using confidential VMs (cVMs) introduces performance challenges, as discussed in the workshop paper [Serverless Confidential Containers: Challenges and Opportunities](https://dl.acm.org/doi/10.1145/3642977.3652097). One approach to mitigate the overhead of starting new cVMs for each request is to preboot cVMs and reuse them across users and requests. Ensuring confidentiality and integrity in this scenario requires, among other things, restoring the cVM's memory to a well-known state between uses.

Leveraging AMD's SEV-SNP extension, we employ a Secure Virtual Machine Service Module (SVSM) running at a higher privilege level (VMPL 1) than the guest VM (VMPL > 1). SEV-SNP provides integrity protection through a Reverse Map Table (RMP), which maintains a one-to-one mapping between system physical addresses and guest physical addresses, including security attributes for each page. Before a private memory page is used, the cVM must validate it using the PVALIDATE instruction, which sets the Validated flag in the corresponding RMP entry.

We explored two approaches to restoring the guest memory to a well-known state:

1. Full Backup Approach: Upon receiving a signal from the guest via a custom protocol after the boot process, the SVSM backs up all validated guest memory pages, capturing a well-known state. 
Upon receiving a second signal, the SVSM attempts to restore these pages. This is similar to a hot swap of the memory from the guest's point of view. However, restoration the pages currently results in a termination of the guest, therefore requiring further work.

1. Trap-on-Write Approach: After receiving a ping from the guest, we clear the WRITE bits in the RMP of all validated pages. Subsequent writes trigger a #VMEXIT(NPF), as outlined in section "15.36.10 RMP and VMPL Access Checks" of the [AMD64 Architecture Programmer’s Manual Volume 2](https://dl.acm.org/doi/10.1145/3642977.3652097). Now, the SVSM should intercept to back up the modified page before restoring the WRITE bit. Then, after receiving a second ping to restore the well-known state, the SVSM restores modified pages and clears the WRITE bits again to maintain control. 
Next steps include tracing the #VMEXIT(NPF) code path in the Linux kernel and delegating the control to the SVSM if the #VMEXIT(NPF) was triggered due to our Trap-on-Write mechanism.
