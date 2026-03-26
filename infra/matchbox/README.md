# Matchbox PXE Boot

Matchbox serves iPXE/PXE configurations to bare-metal servers over the network.

## Setup

1. Run Matchbox server:
```bash
docker run -p 8080:8080 -v $(pwd)/matchbox:/var/lib/matchbox quay.io/coreos/matchbox:latest serve
```

2. Configure DHCP to point new servers to Matchbox (next-server = matchbox IP, filename = ipxe.efi).

3. When a server boots, Matchbox:
   - Reads its MAC address
   - Matches it to a group profile
   - Serves the NixOS installer iPXE script
   - NixOS boots from RAM and begins installation

## Flow
```
New Server (bare metal)
    → DHCP (next-server: matchbox)
    → iPXE chain to matchbox
    → Matchbox serves profile: nixos-install
    → NixOS installer boots from RAM
    → Ansible bootstrap.yml takes over
```
