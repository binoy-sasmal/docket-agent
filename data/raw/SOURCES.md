# Raw data sources

This directory is gitignored except for this file. The raw files themselves
are large, external, and re-downloadable; this file is the record of exactly
what was downloaded, from where, and how it was verified.

## Files

| File | Source URL | Size (bytes) | SHA-256 |
|---|---|---|---|
| `BPIChallenge2019CSV.zip` | https://icpmconference.org/2019/wp-content/uploads/sites/6/2019/02/BPIChallenge2019CSV.zip | 36,720,297 | `372b5a15c30f4a21b370db25b1912cc60ad1104d4198cfd34f8aecb2f4c2425a` |
| `BPI_Challenge_2019.csv` (extracted from the zip above) | -- | 527,457,189 | `7d592fb425690d13011d1b874fe2af63f61a66acfc368ecf87b4ed266e6cdb00` |
| `log_IEEE.xes.gz` | https://icpmconference.org/2019/wp-content/uploads/sites/6/2019/01/log_IEEE.xes_.gz | 16,901,365 | `43edc7abe7b53c75f53f91b6720ba20878de8a3216b5202ae22a0442b92e9c9a` |

Retrieved: 2026-08-31, via direct HTTPS download (URLs checked live first;
both resolved with HTTP 200 and the ICPM 2019 conference page's `http://`
links redirect to `https://` cleanly).

## Licence

**CC BY 4.0** (Creative Commons Attribution 4.0 International). Creator:
Boudewijn van Dongen. Attribution required.

Canonical archival record (4TU.ResearchData): DOI
`10.4121/uuid:d06aff4b-79f0-45e6-8ec8-e19730c248f1`. That record publishes
only `BPI_Challenge_2019.xes` (728,558,522 bytes, MD5
`4eb909242351193a61e1c15b9c3cc814`). The CSV used as the working format in
this project, and the smaller gzipped XES, are published separately on the
ICPM 2019 conference page, not on the 4TU record.

The attribution line used throughout this project (README, `FROZEN.md`):

> Derived from the BPI Challenge 2019 event log (van Dongen, B.F., 2019),
> 4TU.ResearchData, DOI 10.4121/uuid:d06aff4b-79f0-45e6-8ec8-e19730c248f1,
> licensed CC BY 4.0. Structural properties are derived from the log; all
> monetary values, quantities, dispositions and free-text notes are authored
> for this project.

## Cross-check performed at acquisition time

`log_IEEE.xes.gz` was decompressed once (not committed; the 728MB result was
discarded immediately after checking) and its MD5 compared against the
4TU-published value for `BPI_Challenge_2019.xes`:

```
decompressed size : 728,558,522 bytes   (4TU record: 728,558,522 bytes)
decompressed MD5   : 4eb909242351193a61e1c15b9c3cc814
4TU-published MD5  : 4eb909242351193a61e1c15b9c3cc814   -- MATCH
```

This confirms the ICPM-hosted files trace to the same canonical dataset as
the archival 4TU record, independent of and in addition to the row-count
identity check performed in reconnaissance (see `docs/DERIVATION.md`).

This is a one-time integrity check, not the "XES cross-check reader" the
Session 1 plan describes as a *fallback* -- that reader (a streaming
`iterparse` parser used to cross-validate parsed event data against the CSV)
is written only if the ICPM URLs are found dead. They were not.

## Verification

`src/docket/derive/acquire.py` records the same size/SHA-256 values above in
`KNOWN_GOOD` and can re-verify local copies of these files without
re-downloading:

```
python -m docket.derive.acquire
```
