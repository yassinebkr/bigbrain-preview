# Drawing 42 continuation

## Starting state

The continuation retains document `d4f8d16c0e884319b9df205f76f19943`, its confirmed
revision-2 definition and the original SolidCraft 0.28.0 executable. Checkpoint
`6cf61cf08d314f049aa4f72450095c23` contains the continuous passage, eight through
holes and eight counterbores. The two R10 junction fillets, two C10 mouth chamfers
and final independent inspection remain pending at the start of this follow-up.

Call 71 ended with a Codex usage-limit rejection. The campaign ledger retained
that consumed request. The provider accepted call 72 during the new follow-up,
and its precise-geometry observation completed.

## Decision-context diagnosis

After that observation, the next decision packet exceeded the existing
256,000-byte text envelope. The runtime stopped before issuing another provider
request. The measured packet contained repeated native record keys and duplicate
parameter records. Major fields before transport compaction were:

| Field | UTF-8 bytes with ordinary JSON spacing |
| --- | ---: |
| Observations | 176629 |
| Retrieved native command reference | 34939 |
| Initial command reference | 18519 |
| Current design summary | 11919 |
| Historical failures | 11585 |

The ordinary serialized packet measured 301781 bytes with ASCII escapes. The
compact UTF-8 representation after the correction measured 243069 bytes in the
offline sizing check; the live packet additionally carries its authorization
record. The 256,000-byte envelope is unchanged.

## Transport correction

`cad_context.py` encodes repeated native records as column groups. Each group
lists its columns, value rows and original positions. The representation retains
native IDs, exact numeric values, nested attributes, null values and the
distinction between missing and present fields. A repeated parameter observation
may reference the identical `current_design.params` value in the same packet.

Compaction creates a detached transport view. Original checkpoint observations,
measurement files, validation inputs, geometry, hashes and acceptance criteria
remain unchanged. JSON whitespace is compacted without numeric rounding.

Five dedicated tests cover mixed record shapes, exact float round trips,
unchanged source records, nested sketch constraints and equality-checked parameter
references. The context/controller/observation/integration suite passes 67 tests.
The preceding broader CAD regression run passes 124 tests; its report is retained
at `/tmp/cad-completion-followup-20261105.xml`.

Call 73 resumed the model-driven construction using this representation. Final
part qualification remains pending until the finishing and inspection results
are observed.
