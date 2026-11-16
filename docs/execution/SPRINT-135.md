# Synthetic time report preregistration

This Python-only opt-in records the fixed S134 artificial clock report after a
completed S084 quality registration and before any Project action or
Controller request. It does not alter the S084 registration or connect a time
check to dispatch. Existing direct APIs are not a global time gate.

`LocalWorkbench.register_synthetic_time_report` accepts the exact fields
`request_id`, `project_id`, `expected_state_version`,
`registration_request_id`, `registration_sha256` and `report_dir`. The
report directory must be the original S134 six-file synthetic output. The
Project's actual source packet and the report must match the fixed S134
bytes and producer identities. The report is re-read and mechanically
recomputed; it describes an invented naive clock, not a real station, time
zone, licence, or scientific validation.

The manager records the original body and a nonce before the Project writes
an immutable registration and its ownership claim in one Project SQLite
transaction. These are separate transactions. An existing same-ID record is
never adopted in the absence of the original manager intent and Project
claim. A failed or uncertain original request is not automatically reissued.
`resume_synthetic_time_report` takes only the original `request_id` and
`project_id`: it can authenticate the complete original registration and
possibly finish its manager receipt, but cannot create a missing Project
registration. The original report and its producer must remain available.

The manager holds its writer before the Project writer, including through the
terminal manager receipt commit. These locks and repeated byte checks cover
cooperating local processes; they do not prove isolation from a process that
ignores the locks or rewrite all evidence and claims. Hashes are consistency
bindings rather than signatures. Time registration and future IDs do not
reserve actions or prevent older APIs from being called. Any future quality
execution gate needs its own explicit implementation and must recheck the
original registration, source, report, claims and budget at its own commit
boundaries.

This change alters producer identities for new Projects. Existing pinned
Projects remain on their original code and are not upgraded or migrated.
The synthetic fixture and its report do not approve or enable UCI data or
any real research.

Independent verification: HEAD `4b8980b7836bf559153e99a353c468b3800e6506` plus 627-item manifest SHA `5ce849ef060c5d50d0f4ca509591936051416cd847760472348a98423009bb8f` remained consistent; independent reviewer ran 53/53 synthetic tests, and the test author separately reran 16/16 in a new process. Writer-lock testing uses cooperative flock and transaction interruption uses injected faults; neither establishes real SIGKILL or OS isolation for this new entrance. The registration does not gate dispatch or authorize real UCI data.
