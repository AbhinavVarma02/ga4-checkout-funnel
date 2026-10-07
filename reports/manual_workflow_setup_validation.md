# P5.9 approved resource and IAM setup

**Resource/IAM portion complete; owner credentials pending.** The owner replied
`go` to the setup-only gate after `f17f9fc0b3c0b6b611a6ff9a5c619dca4b6d43ff`.
Source: `warehouse_builds.p5_9_resource_iam_setup` in
[metrics.json](metrics.json). The original [exact scope](manual_workflow_native_validation.md)
remains the execution record; do not repeat its creation commands.

Read-only native checks confirmed both proposed names absent before any
mutation. The service-account list was empty; BigQuery dataset GET returned
NotFound. The execution wrapper repeated both checks and saved the existing
project IAM policy, then performed exactly the approved three mutations:

1. Created `ga4-github-dbt@ga4-checkout-funnel.iam.gserviceaccount.com` in
   `ga4-checkout-funnel` with the reviewed display name.
2. Added its unconditional project `roles/bigquery.jobUser` binding.
3. Created empty US `ga4-checkout-funnel.ga4_ci` with exactly dataset OWNER for
   `projectOwners` and WRITER (Data Editor) for this service account.

Execution began at **2026-10-06 23:41:04.663044 UTC** and completed verified
readback at **23:41:12.248256 UTC**. Native gcloud describe verifies the account's
email/project/active state. Fresh project-policy readback verifies its only
direct project grant is Job User. Removing that new member from the normalized
policy produces the complete original binding set, preserving every other
role/member/condition. Policy etag changes are expected.

BigQuery dataset GET/table-list readback verifies US, zero tables, the exact two
reviewed access entries and null default table/partition expirations. Dataset
creation fails on an existing name; no existing policy or dataset was replaced.
There was no project-wide Data Editor/Admin grant or write to existing
raw/analyst/replay data. These checks establish resource metadata and explicit
grants; service-account authentication and native workflow execution are still
unverified.

The initial sandbox gcloud read failed on its credential-cache filesystem;
approved escalation succeeded. The initial dataset GET waited on sandbox
network access and was interrupted before any cloud mutation; the approved
network-only read completed. The separately escalated approved setup wrapper
exited zero and retained each mutation/readback receipt. No credential files or
values were displayed. Noncredential receipts and exact executed wrapper are
retained under `reports/.checks/p5_9_setup/`, with hashes in the source key.

All pre-existing metric values are preserved with one additive native setup
section. Owner Power BI bytes/index/status, all 300 owner files, the 95-row CSV,
canonical exports/configs, all 44 saved Gate #23 artifact hashes, original
backfill cache and comparison receipts remain unchanged. The existing P5.9
preparation/test/code evidence is historical and unchanged; only the current
gate/handoff status is updated. No code/dependency change or test rerun was
needed. Documentation links, whitespace and preservation checks pass.

**Zero SQL, dry-run query, raw load, dbt build or Airflow action was submitted.**
Recorded query usage stays **355.4794921875 GiB**, with the original **512 GiB**
boundary intact. This resource setup records no new query jobs or query-byte
addition; it does not inspect account-wide costs, credits or an invoice.
The setup script performed no key/secret change, publication, workflow dispatch, tag or
deletion; owner credential completion remains unconfirmed.

The approved **owner-only** action remains: create this account's JSON key in
[Google Cloud Console](https://console.cloud.google.com/iam-admin/serviceaccounts?project=ga4-checkout-funnel),
keep it outside the repository, and add repository secret **GCP_SERVICE_ACCOUNT_KEY**
in [GitHub repository settings](https://github.com/AbhinavVarma02/ga4-checkout-funnel/settings/secrets/actions).
Confirm completion without sharing the value. Human Step #4 stays partially
complete until those owner steps are confirmed and nonsecret presence is checked.
P5.9 remains blocked on those credentials and the separate #25 publication and
cost/cloud-write execution gates. Existing approvals authorize no repeat,
automatic workflow dispatch, permission expansion or resource cleanup.
