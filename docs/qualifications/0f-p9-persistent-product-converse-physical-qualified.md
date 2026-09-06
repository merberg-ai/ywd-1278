# 0F-P9 persistent product UNPROTO/CONVERSE physical qualification

Status: **PHYSICALLY QUALIFIED** on 2026-09-06.

## Physically exercised product source

The live appliance was staged from:

- branch: `dev-0f-p9-persistent-product-converse`
- commit: `130f76ffbdf4e77b398e33d63814be3c965dce6e`

P9 did not replace or modify the 0F-P8 product CONVERSE/modem/channel-access implementation. It productized that already-qualified composition through the normal installed source, normal Python environment, `ywd-1278.service`, persistent product TX authority, and the ordinary product Telnet console.

## RF profile

- frequency: `145.050 MHz`
- TX power: `200/255`
- source: `KJ6YWD-10`
- normal service: `ywd-1278.service`
- temporary qualification daemon: **not used**
- automatic TX retry added by P9: **no**
- firmware write required by P9: **no**
- option-byte write required by P9: **no**

## Live result

The operator reported the complete staged normal-service sequence successful and supplied independent receiver evidence from the live packet channel.

The following one-digipeater path was exercised successfully:

```text
UNPROTO JIM VIA YWDNOD
```

Independent receiver examples included:

```text
KJ6YWD-10>JIM,YWDNOD:hello test 123
KJ6YWD-10>JIM,YWDNOD:hello test
```

The operator also exercised a chained two-digipeater path successfully:

```text
UNPROTO JIM VIA YWDNOD,KRDG
```

Independent receiver evidence included the direct source-path frame and a returned repeated copy:

```text
KJ6YWD-10>JIM,YWDNOD,KRDG:hello test
KJ6YWD-10>JIM,YWDNOD*,KRDG*:hello test
```

That supplemental test closes the P8 gap for this **specific** chained path. It does not claim arbitrary digipeater-chain qualification.

## Qualified boundary

0F-P9 now physically qualifies:

1. software-only installation of the P9 productization layer without a firmware operation;
2. explicit persistent product TX authority at the already-qualified `145.050 MHz / power 200` profile;
3. the normal installed systemd service as the owner of the real product packet engine;
4. normal product Telnet `UNPROTO`/`CONVERSE` RF operation;
5. `UNPROTO JIM VIA YWDNOD`;
6. `UNPROTO JIM VIA YWDNOD,KRDG`;
7. independent over-air observation of the configured AX.25 source/path behavior;
8. returned digipeated traffic in the live packet environment;
9. reuse of the frozen P8 no-scheduler/no-new-retry product TX composition;
10. cleanup through the explicit persistent-TX disable boundary after qualification.

## Still outside this slice

P9 does **not** qualify:

- arbitrary digipeater paths beyond the specifically observed vectors;
- beacon/BTEXT/ID RF behavior beyond previously frozen evidence;
- connected-mode `CONNECT` behavior beyond the separate 0G lineage;
- automatic TX retry;
- scheduled transmissions;
- forwarding activation.

Machine-readable evidence is frozen in:

`firmware/qualification/0f-p9-persistent-product-converse-target-pi.json`

and enforced by:

`tests/persistent_product_converse_0f_p9_physical_evidence_contract_test.py`
