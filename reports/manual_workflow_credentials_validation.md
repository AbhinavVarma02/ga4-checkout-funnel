# P5.9 owner credentials: read-only verification and Gate #25

**Human Step #4 is complete. P5.9 execution remains gated.** The owner confirms
creating the intended JSON key and adding `GCP_SERVICE_ACCOUNT_KEY`, without
sharing the key or storing it in this repository. Read-only metadata supports
that setup; source `warehouse_builds.p5_9_owner_credentials_verification` in
[metrics.json](metrics.json).

GitHub lists repository secret **GCP_SERVICE_ACCOUNT_KEY**, updated at
**2026-10-06 23:53:04 UTC**. IAM lists one **USER_MANAGED / GOOGLE_PROVIDED** key
on `ga4-github-dbt@ga4-checkout-funnel.iam.gserviceaccount.com`, valid from
**23:48:22 UTC** and within its recorded validity bounds. Only key identity/type
and validity metadata were inspected; neither private key material nor the
GitHub secret value was read. Secret contents and successful authentication
remain to be established by the separately approved workflow.

Fresh BigQuery metadata at **2026-10-07 00:08:53.401819 UTC** verifies `ga4_ci`
is still in US, has zero tables, the exact reviewed WRITER/projectOwners OWNER
entries and null table/partition expiration defaults. These reads use the
existing owner ADC, not the new service-account secret. No SQL or query dry run
was submitted.

## Publication is still a prerequisite

Live GitHub main is **2f18f04ae8ae9b365a082078418b09e55713017a**. Its
[CI run 37328060786](https://github.com/AbhinavVarma02/ga4-checkout-funnel/actions/runs/37328060786)
and `checks` job completed successfully, with every reported step successful.
This is evidence for that older commit only. The read-only manual workflow
listing still returns no runs.

GitHub contents metadata identifies the published workflow blob as
`619d9d5a9c4d7f0c935e9d5891b7777bb3e9af6d`, matching the exact local Git blob at
that remote SHA. Its [published code](https://github.com/AbhinavVarma02/ga4-checkout-funnel/blob/2f18f04ae8ae9b365a082078418b09e55713017a/.github/workflows/dbt_bigquery.yml)
still targets **ga4_analytics** and defaults to the complete sample window.
It differs from the reviewed isolated `ga4_ci` workflow. Local
`e3d2251f1e648b46714f0f815066ff8de98a43a6` is 55 commits ahead of live main;
this documentation/evidence closeout adds another local commit. A remote
comparison with the unpublished local head returned 404; the local Git ancestry
and verified live branch/blob establish the publication difference.

The user's current instruction authorizes read-only verification. It supplies
no publication or manual execution approval. **Gate #25 cannot dispatch the
prepared workflow until publication and matching fresh CI are verified.**
The [existing Gate #25 scope](manual_workflow_native_validation.md)
requires separate approval for a fast-forward publication, followed by separate
cost/cloud-write approval for one dispatch. Freeze and display the literal
closing commit SHA, commit range and these exact commands before execution:

```bash
git push origin FULL_REVIEWED_LOCAL_SHA:refs/heads/main

gh workflow run dbt_bigquery.yml \
  --repo AbhinavVarma02/ga4-checkout-funnel --ref main \
  -f project_id=ga4-checkout-funnel \
  -f reviewed_commit=FULL_REVIEWED_LOCAL_SHA \
  -f confirm_cloud_write=go
```

The placeholders are filled after this local closeout; commands are review
templates, not authorization. The publication command alone does not authorize
dispatch. Execution scope remains only public `events_20201101`, seven sandbox
models and fourteen data tests in US `ga4_ci`, 128 MiB per query, first attempt
only, fresh model/test preflights, no native unit work, no raw/replay/backfill,
and separate API accounting. Per-query caps are not a cumulative billing cap;
native estimates, billed bytes and authentication remain pending.

Read-only network/SDK-cache failures were resolved by approved escalation.
The metadata receipts are retained under `reports/.checks/p5_9_credentials/`.
All earlier metric values, backfill/cache/comparison evidence, 95 CSV rows,
canonical exports/configs and all 300 owner Power BI files/index/status remain
preserved. Recorded usage is still **355.4794921875 GiB**. No code/dependency
change, test rerun, cloud mutation, key/secret mutation, SQL, Airflow action,
push, tag, workflow dispatch or deletion occurred.
