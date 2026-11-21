# SolidCraft 0.45.0 compatibility probe

The Linux x86-64 CLI came from the
[official v0.45.0 release](https://github.com/tangency-labs/solidcraft/releases/tag/v0.45.0).
The extracted archive matched its published SHA-256
`78170f546e1442db9d14637a4b8a8e6b39b543009d3d3d857cbd65f09afa37f8`.
The test used temporary copies and isolated XDG directories.

| Case | Observed result |
| --- | --- |
| Drawing 42 revision 5, created in 0.28.0 | Opened and exported one closed solid in 0.45.0. The migrated document retained 28 feature entries. |
| Independent STEP integration | 28,094,977.13241519 mm³ in 0.45.0 versus 28,094,977.13234817 mm³ in the published reference. |
| Drawing 42 local sections | All 28 probe calls returned without error. Twelve interval records were exactly equal. The remaining records had numerical differences that require a tolerance-by-tolerance comparison. |
| Enclosure assembly | Opened and exported all 11 bodies. The migrated document retained eight feature entries. Editing the shared fastener width to 4 mm recomputed one definition. The rigid joints remained solved. |
| Backward open in 0.28.0 | Rejected the migrated assembly. The native document format changed from 45 to 63. |

The migration decision remains open. The pinned 0.28 runtime controls retained
checkpoints. The next compatibility cases are the helix volume, local cut
reconstruction, repeated assembly measurements and Windows. An upgrade must
preserve the original revision lineage and retain original-format files for
rollback.
