# Lab 21 -- Network carriers: the carrier keeps moving

| | |
|---|---|
| Domain | network |
| Algorithms | dns-tunnel, ip-id, inter-packet-timing |
| Detectors | `dns_tunnel`, `ip_id_entropy`, `timing_channel` |
| Measured FPR | 0/12 on seeded background captures |
| Detection | 12/12 on all three channels, at their stated payload floors |
| Evidence ceiling | E4 for DNS and timing; **E1** for IP ID |

## There is no file

Every other carrier here is a finished object an analyst holds. A capture is a
*window* onto a conversation that started before it and continued after. Every
count in this lab is a rate, because a count without its window is not a
measurement: twenty suspicious queries means nothing until you know whether the
capture is one second or one hour long.

## Three channels, three legitimate twins

**DNS tunnelling** puts the payload in query labels. Its twin is CDN sharding
and reputation lookups, whose hostnames are long, high-entropy and innocent.
Entropy alone flags them; the discriminator is that **resolvers cache**. Real
traffic repeats heavily -- measured unique-query ratios of 0.05 to 0.25 in the
background corpus -- while a tunnel never repeats, because every query carries
different bytes. Volume, uniqueness and label length together, or nothing.

**IP identification** puts two bytes per packet in the 16-bit ID field. Its
twin is every operating system: Linux writes zero for atomic datagrams, older
stacks count, some randomise. The signal is not "the IDs look random" -- it is
that **one host changed its mind mid-capture**, 100 distinct non-zero IDs
sitting among 1,100 zeros from the same source.

**Inter-packet timing** puts the payload in the gaps. Its twin is jitter, which
is large and continuous. A channel quantises: measured top-two-value share is
0.027 to 0.031 in background traffic and above 0.5 once a channel is present,
an order of magnitude apart.

## IP ID stops at E1, and that is the finding

The other two channels reach E4. IP ID does not, and the reason is written into
the detector rather than left to the analyst: **a randomising TCP/IP stack
produces exactly the same evidence.** The finding says so in its own claim
text. Distinguishing the two needs a baseline for what that host normally does,
which is the same-source requirement the evidence ladder has demanded since T0,
arriving here as a requirement about a *host* rather than a camera.

## Detection floors, stated

| channel | floor | why |
|---|---|---|
| DNS tunnel | ~2,000 bytes | below 30 queries/min the rate test does not fire |
| IP ID | 16 bytes | needs 8 patched packets to be a population |
| timing | 12 bytes | needs enough gaps for the top-two share to mean anything |

The DNS floor is worth dwelling on. In a 90-second capture, a 1,500-byte
payload is 60 queries -- 39/min, just under the threshold -- and goes
undetected 0/6. At 2,000 bytes it is 6/6. **A slow tunnel in busy traffic
hides**, and no threshold choice makes that go away; it moves the floor.

## The payload's own entropy changes the answer

A tunnel carrying compressed or encrypted data produces unique labels and
unique IDs, and the uniqueness signals work. A tunnel carrying **repetitive
plaintext** produces repeating labels: measured unique ratio 0.01 on a
2,000-byte run of one character, against 1.00 for random bytes of the same
length. The uniqueness detector reports nothing.

That is a genuine hole and it is worth naming plainly: an unsophisticated
sender who does not compress accidentally defeats a detector aimed at
sophisticated ones. Detectors built on "covert traffic looks random" inherit
this, and the answer is a second signal that does not depend on entropy --
volume and label length still fire, which is why the DNS test requires all
three rather than any one.

## Reproduce

```bash
python3 -m pytest tests/test_labs_h.py -q
```

## The parser

`steganalysis.pcap` walks libpcap records and Ethernet/IPv4/TCP/UDP/DNS headers
without asking a decoder anything. Cross-validated against tshark 4.2.2: 6,400
field comparisons across `ip.id`, `ip.proto`, `ip.flags.df` and `tcp.seq_raw`,
plus 344 DNS query names, **zero mismatches**, and every generated IPv4
checksum verified good by tshark.

## What it teaches

Two of these channels survive content inspection entirely -- the timing channel
does not alter a single byte of any packet. What defeats them is not looking
harder at packets but looking at the *shape of the conversation*: how often,
how varied, how evenly spaced. That is a different instrument from everything
else in this repository, and it needs a window length attached to every number
it produces.

---

[Chinese version](README_zh.md)
