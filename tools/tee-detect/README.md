## SC2 TEE Detection

This script is a very, _very_, simplified mechanism to check whether we are
running in an SNP-enabled or TDX-enabled box.

It is deliberately simple and incomplete. It assumes the server has been set up
properly with either SNP or TDX, and it just works out which one it is.

To check if you have a _correct_ installation, please refer to more complete
tools like [`snphost`](https://github.com/virtee/snphost).
