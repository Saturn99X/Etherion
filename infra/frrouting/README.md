# FRRouting (BGP) Configuration

FRRouting (FRR) announces Etherion's IP addresses to the global internet using BGP.

## What This Does

When you own IP addresses (your own ASN), FRRouting tells upstream providers:
"The IP range 203.0.113.0/24 is reachable via this router."

If you have racks in multiple locations (Douala + Singapore), each rack runs FRR.
BGP automatically routes users to the nearest rack via anycast.

## Setup

1. Get an ASN from your RIR (ARIN/RIPE/AFRINIC)
2. Get IP space from your provider or RIR
3. Update `frr.conf` with your real ASN, IP block, and upstream peer
4. Install and start FRR: `sudo systemctl start frr`

## Local Testing

No BGP needed for local dev. This is only relevant for production bare-metal with real IP addresses.
