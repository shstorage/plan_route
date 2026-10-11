# P06: project persistence and development result screen

The domain JSON remains the only project source of truth. A saved file wraps
that document with schema version, monotonic local revision, UTC modified time,
and SHA-256 document hash. The `GET /api/projects/{project_id}` body is the
EngineeringProject itself; revision, time, and hash are exposed as response
headers so clients can use the same JSON for validation and routing.

The server chooses the fixed `data/projects/` directory. IDs must match the
domain identifier grammar and the resolved target must remain inside that
directory. Saving holds a process-local lock while reading the previous
revision, writes a temporary file in the same directory, fsyncs, then atomically
replaces the target. A failed replacement leaves the previous revision intact.
This is a local single-process store; multi-worker updates need a transactional
database or cross-process lock in a later phase.

The P06 UI edits the EngineeringProject JSON text, sends it directly to the
existing validation and routing APIs, and displays status, metrics, violations,
and world-coordinate route points. It does not derive domain state from rendered
pixels. Visual geometry editing is intentionally reserved for P07.
