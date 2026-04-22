# APA — Environment Promotion Runbook

This document tracks every change made during local development
and exactly what needs to happen when promoting to DEV → QA → PROD.

**Golden rule: If you fix something locally, it goes in a migration or
this runbook. Never rely on memory.**

---

## How to promote to a new environment

```
Local → DEV → QA → PROD

Each promotion = git push + alembic upgrade head + restart
```

The CI/CD pipeline (`.github/workflows/cicd.yml`) runs
`alembic upgrade head` automatically before deploying. So every
migration in `alembic/versions/` runs automatically on every environment.

---

## Migrations — run automatically on every environment

| Migration | What it does |
|-----------|-------------|
| `0001_initial.py` | Base tables: users, documents, invitations |
| `0002_user_role.py` | Add role column to users |
| `0003_refresh_tokens.py` | Add refresh_tokens table |
| `0004_comments_and_invitation_revoke.py` | Add comments, invitation revoke |
| `0005_workflow_versions_assignments.py` | Add workflow_state, document_versions |
| `0006_phase1_medicare_fields.py` | Add document_type, extracted_fields, etc. |
| `0007_jsonb_enums_release_schema.py` | JSONB columns, enum types |
| `0008_phase2345_schema.py` | Phase 2-5: vault, medications, timeline, financial |
| `0009_fix_all_enums.py` | **Fix all 27 document types + missing enum values** |

**To apply all migrations on a new environment:**
```bash
cd backend
alembic upgrade head
```

---

## Manual fixes applied locally — now covered by migration 0009

These were fixed manually on the local database and are now
permanently tracked in migration `0009_fix_all_enums.py`:

### 1. Missing document_status_enum values
```sql
-- Fixed by 0009_fix_all_enums.py
ALTER TYPE document_status_enum ADD VALUE IF NOT EXISTS 'quarantined';
ALTER TYPE document_status_enum ADD VALUE IF NOT EXISTS 'uploading';
```

### 2. Missing malware_scan_status_enum values
```sql
ALTER TYPE malware_scan_status_enum ADD VALUE IF NOT EXISTS 'skipped';
```

### 3. Missing workflow_state_enum values
```sql
ALTER TYPE workflow_state_enum ADD VALUE IF NOT EXISTS 'needs_review';
ALTER TYPE workflow_state_enum ADD VALUE IF NOT EXISTS 'waiting_on_user';
ALTER TYPE workflow_state_enum ADD VALUE IF NOT EXISTS 'resolved';
```

### 4. Missing document_type_enum values (22 types were missing)
```sql
-- All 22 types added by 0009_fix_all_enums.py
-- electricity_bill, natural_gas_bill, social_security_notice, etc.
```

---

## Code fixes applied locally — already in source code

These file changes are already committed in source and deploy
automatically when you push to GitHub:

| File | What was fixed |
|------|---------------|
| `app/db/enums.py` | Added all 27 DocumentType values |
| `app/db/enums.py` | Added RESOLVED to WorkflowState |
| `app/api/v1/caregiver.py` | Added GET /members route |
| `app/api/v1/vault.py` | Added GET /items route |
| `app/api/v1/analytics.py` | Added GET /financial-alerts route |
| `app/services/bill_intelligence.py` | Fixed electricity bill detection (Coserv/TexReg) |
| `alembic/env.py` | Fixed sys.path + bypassed configparser % bug |

---

## Environment variables — set per environment in AWS Secrets Manager

These are NOT in git. Set them manually in AWS Secrets Manager
for each environment before first deploy.

| Secret name | DEV | QA | PROD |
|-------------|-----|----|------|
| `apa-{env}/secret-key` | generate with `python -c "import secrets; print(secrets.token_hex(64))"` | same | same |
| `apa-{env}/database-url` | RDS endpoint for that env | | |
| `apa-{env}/anthropic-key` | `sk-ant-...` | same key or separate | same |
| `apa-{env}/redis-url` | ElastiCache endpoint | | |
| `apa-{env}/minio-access-key` | S3 key for that env | | |
| `apa-{env}/smtp-host` | SES or SendGrid | | |
| `apa-{env}/twilio-sid` | Twilio account SID | | |

---

## .env settings for local development

These go in `backend/.env` — never committed to git:

```env
ENVIRONMENT=development
LLM_PROVIDER=anthropic
ANTHROPIC_API_KEY=sk-ant-...   ← rotate if leaked
OPENAI_API_KEY=sk-proj-...     ← rotate if leaked
SECRET_KEY=<64 char hex>       ← generate fresh
AUDIT_LOG_RETENTION_DAYS=2555
DATABASE_URL=postgresql://postgres:yourpassword@localhost:5432/paperwork_db
REDIS_URL=redis://localhost:6379/0
MINIO_ACCESS_KEY=minioadmin
MINIO_SECRET_KEY=minioadmin
MALWARE_SCANNING_ENABLED=false  ← set true when ClamAV is running
```

---

## Checklist before pushing to DEV

- [ ] All local manual DB fixes are in a migration (`alembic upgrade head` runs clean)
- [ ] `enums.py` matches what Claude/heuristic can return
- [ ] All new API routes are in `router.py`
- [ ] `.env` changes documented here under Environment Variables
- [ ] API keys rotated if exposed in any chat/log
- [ ] `alembic upgrade head` runs without errors locally
- [ ] `pytest tests/ -v` passes locally
- [ ] No hardcoded secrets in any source file

---

## Checklist before pushing to PROD

Everything above, plus:
- [ ] QA testing sign-off
- [ ] GitHub environment "production" approval gate enabled
- [ ] AWS Secrets Manager has prod secrets populated
- [ ] RDS Multi-AZ enabled
- [ ] CloudWatch alarms configured
- [ ] BAA signed with AWS and Anthropic

---

## Adding a new fix in the future

1. Make the code change in the relevant file
2. If it changes the database → create a new migration:
   ```bash
   alembic revision -m "describe_your_change"
   # edit the generated file in alembic/versions/
   alembic upgrade head   # test locally
   ```
3. Add an entry to this runbook under "Code fixes" or "Migrations"
4. Push to git → CI/CD handles the rest
