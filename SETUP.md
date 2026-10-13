# Setup and portability guide

## Prerequisites

- A Databricks workspace with Unity Catalog and serverless notebook or job compute.
- Databricks CLI with Declarative Automation Bundle dashboard support. CLI 0.281.0 or newer is required.
- OAuth or Azure CLI authentication configured for a named CLI profile.
- A Unity Catalog catalog where the runner has `USE CATALOG` and `CREATE SCHEMA`.
- Permission to create tables in the selected schema.
- Access to `databricks-qwen3-embedding-0-6b` through `ai_query`. This model is Public Preview and might not be available in every cloud, region, or workspace.
- Outbound access to `huggingface.co` for the pinned LaBSE model revision.
- A running SQL warehouse and its warehouse ID for the dashboard.

Optional capabilities:

- `SELECT` on `system.billing.usage` for the cost chart. Without it, the job writes an empty typed cost table and continues.
- Job-tag propagation into billing system tables. Without matching usage tags, the cost table can be empty.

## Use in your workspace

### 1. Authenticate

```bash
databricks auth login --host <workspace-url> -p <profile>
databricks auth describe -p <profile>
```

Do not commit credentials or workspace URLs into the repo.

### 2. Select deployment values

Required bundle variables:

- `catalog`: target Unity Catalog catalog (example: `main`).
- `warehouse_id`: SQL warehouse ID used by the AI/BI dashboard.

Optional:

- `schema`: target schema. The default is `multilingual_warranty_demo_<current-user-short-name>`.

The schema should be dedicated to this demo because reruns overwrite its demo tables.

### 3. Validate

From the repository root:

```bash
databricks bundle validate --strict -p <profile> \
  --var="catalog=<catalog>,warehouse_id=<warehouse-id>"
```

To override the schema:

```bash
databricks bundle validate --strict -p <profile> \
  --var="catalog=<catalog>,schema=<schema>,warehouse_id=<warehouse-id>"
```

### 4. Deploy and run

```bash
databricks bundle deploy -p <profile> \
  --var="catalog=<catalog>,warehouse_id=<warehouse-id>"

databricks bundle run warranty_embedding_demo -p <profile> \
  --var="catalog=<catalog>,warehouse_id=<warehouse-id>"
```

The job runs two tasks in order:

1. Generate synthetic data and compare Qwen3 with LaBSE.
2. Re-embed simulated weekly batches, evaluate drift and quality, log MLflow evidence, and populate dashboard tables.

The dashboard is deployed with `dataset_catalog` and `dataset_schema`, so its SQL uses unqualified table names and binds to your catalog and schema at deploy time.

## Interactive Run All

If CLI deployment is not desired:

1. Import both `.ipynb` files under `src/notebooks/`.
2. Attach the base notebook to serverless compute.
3. Set `catalog` and `schema` widgets.
4. Run All in `multilingual_warranty_qwen3_vs_labse.ipynb`.
5. Attach `05_monitoring_and_aiops.ipynb` to serverless compute.
6. Use the same widget values and Run All.
7. Import `src/dashboards/warranty_monitoring.lvdash.json`, then select the same catalog, schema, and a SQL warehouse in the dashboard settings.

The notebooks use Python variables and widgets rather than custom `spark.conf.set` keys, so they work with Spark Connect serverless and classic compute.

## Adopt (your own claim table)

Required columns for a drop-in replacement of the synthetic corpus:

| Column | Role |
|---|---|
| `claim_id` | Stable unique id |
| `defect_id` | Ground-truth defect or issue label (used for purity / ARI) |
| `language` | Language code (e.g. `en`, `ko`, `es`, `de`) |
| `claim_text` | Free-text claim body |

Steps:

1. Create or grant a schema for the demo outputs.
2. Replace the generator section in the base notebook with a read from your table (same column names), or write a staging view that aliases your columns to this contract.
3. Run base, then Day-2, with the same catalog and schema.
4. Keep one embedding model per index (do not blend Qwen3 and LaBSE vectors).
5. Recalibrate `MIN_CLUSTER_PURITY`, `MIN_XLING_RETRIEVAL`, and `OOD_SIM_THRESHOLD` on labeled historical batches before production use.

## Update (pull, change config, redeploy)

| Situation | Action |
|---|---|
| New commits from GitHub | `git pull` → `bundle validate` → `bundle deploy` → `bundle run` |
| You edited notebooks or `resources/*.yml` | `bundle deploy` then `bundle run` |
| Temporary catalog/schema for one run | CLI `--var="catalog=...,schema=...,warehouse_id=..."` |
| Interactive one-off | notebook widgets (does not edit the bundle) |
| Team defaults | set `variables` / per-target overrides in `databricks.yml` |
| Tear down job + dashboard | `databricks bundle destroy -p <profile>` |
| Tear down tables | only on a demo-dedicated schema: `DROP SCHEMA \`<catalog>\`.\`<schema>\` CASCADE` |

`bundle destroy` removes deployed resources. It does **not** drop Unity Catalog tables created by notebook SQL.

## Air-gapped workspaces

LaBSE is pinned to Hugging Face revision `836121a0533e5664b21c7aacc5d22951f2b8b25b`. If outbound model download is blocked:

1. Mirror that revision into an approved artifact repository or Unity Catalog volume.
2. Change `LABSE_MODEL` to the mirrored path.
3. Keep `LABSE_REVISION` documented with the mirrored artifact checksum.

The managed Qwen3 endpoint also requires workspace entitlement and network access to the Databricks service.

## Validation and tests

Run local static tests:

```bash
python -m unittest discover -s tests -v
```

The tests check notebook structure, dashboard parameterization, and required repository assets. They do not call Databricks.

For release validation, also run:

1. `databricks bundle validate --strict`.
2. Deploy to a fresh schema.
3. Run the workflow twice to verify idempotency.
4. Open the dashboard and execute each dataset query.
5. Repeat once with no billing-system permission to verify graceful degradation.

## Cleanup

```bash
databricks bundle destroy -p <profile> \
  --var="catalog=<catalog>,warehouse_id=<warehouse-id>"
```

Only for a schema dedicated to this demo:

```sql
DROP SCHEMA `<catalog>`.`<schema>` CASCADE;
```

Review the catalog and schema carefully before running destructive SQL.

## Known limitations

- Qwen3 is Public Preview and can be unavailable or change independently of this repository.
- Synthetic metrics do not establish production accuracy, drift thresholds, cost, latency, or business impact.
- The LaBSE comparison collects 144 rows to the Python process. This is intentional for a small evaluation corpus and is not a production-scale embedding pattern.
- The demonstration overwrites named tables in its selected schema. Use an isolated schema per user or environment.
- Billing usage can lag and depends on permissions and tag propagation.
- This repository is intended for internal reuse. Add an organization-approved license before wider redistribution.
