# Maker product direction

## Audience and value

The initial audience is makers and hobbyists. Candidate tasks include replacement
parts, enclosures, brackets, adapters and small mechanisms. The proposed value is
an editable, printable model generated from language, sketches or dimensioned
drawings, with explicit dimensional checks and clarification where needed.

Commercial viability remains to be measured: successful completion rate, user
interventions, frequency of use, willingness to pay and support cost.

## Deployment and protection

Compare local, hybrid and hosted deployment. A hybrid candidate keeps SolidCraft,
files and interactive rendering local, with proprietary orchestration and model
access on the service. Source transmission and offline behavior require explicit
architecture decisions. Keep the current SolidCraft version during qualification.

Local software can be inspected and modified. Compilation and obfuscation can
increase the effort required to copy it. Server-held orchestration reduces the
amount of proprietary logic distributed. Provider secrets belong on the server.

Credits require server authority: operation identity, authorization, atomic budget
reservation, observed usage settlement, concurrency limits and an auditable
ledger. Retries and duplicate submissions must preserve operation identity.
Define cancellation, failure charging, refunds and unknown usage behavior before
launch. An administrative dashboard should support accounts, permissions, costs,
blocked tasks, refunds and traced interventions.

Subscription with included credits and optional top-ups is a pricing hypothesis.
Compare it with credit purchases. Measure model cost, CAD compute time, peak
memory, storage and failure/repair cost per successful project before pricing.

## Assemblies

Assemblies are an important product capability. Qualification should progress
through multiple editable parts, constrained assemblies with interference checks,
then articulated mechanisms. Preserve component identities, reusable instances,
revisions, placement constraints and dependency relationships.

A proposed first qualification is an enclosure, lid and four fasteners: editable
parts, constrained placement, specified clearance, interference checks and a
dimension change that preserves assembly relationships. Runtime evidence is
required before promising this capability commercially.

## Work order

Complete tracking consistency, then integrate SolidCraft and progressive CAD
observations. Qualify one or two additional supplied drawings, then implement and
qualify assemblies. Production architecture and commercial implementation follow
a dedicated review with the user.
