.PHONY: reset-local-db seed-local-locations backup-postgres verify-postgres-backup

reset-local-db:
	cd backend && .venv/bin/python scripts/reset_local_db.py $(ARGS)

seed-local-locations:
	cd backend && .venv/bin/python scripts/seed_local_locations.py

backup-postgres:
	cd backend && .venv/bin/python scripts/postgres_backup_restore.py backup "$(BACKUP)"

verify-postgres-backup:
	cd backend && .venv/bin/python scripts/postgres_backup_restore.py verify "$(BACKUP)"
