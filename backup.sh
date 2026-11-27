#!/usr/bin/env bash
# Daily backup of everything that matters: every store DB, uploads, and .env.
#
#   ./backup.sh                 # run now (cron runs it daily, see DEPLOY.md "Backups")
#   KEEP_DAYS=30 ./backup.sh    # keep more days
#
# Output: $BACKUP_DIR/<YYYY-MM-DD_HHMM>/{<store>.db, uploads.tar.gz, env}, newest KEEP_DAYS kept.
# DBs are copied with SQLite's online backup API, so it's safe while the app is taking orders
# (a plain `cp` of a WAL-mode database can capture a half-written state). Each copy is checked
# with PRAGMA integrity_check; any failure exits non-zero and leaves the folder marked FAILED.
set -euo pipefail
cd "$(dirname "$0")"

DATA_DIR="${DATA_DIR:-$PWD/data}"
BACKUP_DIR="${BACKUP_DIR:-$(dirname "$PWD")/serveflow-backups}"
KEEP_DAYS="${KEEP_DAYS:-14}"
stamp="$(date -u +%Y-%m-%d_%H%M)"
out="$BACKUP_DIR/$stamp"

umask 077  # backups hold customer names/phones and the .env secrets: owner-only
mkdir -p "$out"
trap 'mv "$out" "${out}_FAILED" 2>/dev/null; echo "✗ Backup failed: see ${out}_FAILED" >&2' ERR

python3 - "$DATA_DIR" "$out" <<'PY'
import pathlib, sqlite3, sys
src, dst = pathlib.Path(sys.argv[1]), pathlib.Path(sys.argv[2])
dbs = sorted(src.glob("*.db"))
if not dbs:
    sys.exit(f"no store databases found in {src}")
for p in dbs:
    target = dst / p.name
    with sqlite3.connect(f"file:{p}?mode=ro", uri=True, timeout=30) as s, sqlite3.connect(target) as d:
        s.backup(d)
    with sqlite3.connect(target) as d:
        ok = d.execute("PRAGMA integrity_check").fetchone()[0]
        orders = d.execute("SELECT COUNT(*) FROM orders").fetchone()[0]
    if ok != "ok":
        sys.exit(f"integrity check failed for {target}: {ok}")
    print(f"  {p.name}: {orders} orders, {target.stat().st_size // 1024} KB")
PY

if [ -d "$DATA_DIR/uploads" ]; then
  tar -czf "$out/uploads.tar.gz" -C "$DATA_DIR" uploads
fi
[ -f .env ] && cp .env "$out/env"
cp "$DATA_DIR/signups.jsonl" "$out/" 2>/dev/null || true

# keep the newest KEEP_DAYS backups
ls -1d "$BACKUP_DIR"/20*/ | sort -r | tail -n +"$((KEEP_DAYS + 1))" | while read -r old; do rm -rf "$old"; done

echo "✓ Backup $out ($(du -sh "$out" | cut -f1)); $(ls -1d "$BACKUP_DIR"/20*/ | wc -l) kept in $BACKUP_DIR"
