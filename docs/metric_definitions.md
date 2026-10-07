# Metric definitions and model design

The project analyzes Google's public GA4 ecommerce export for November 1, 2020
through January 31, 2021. The stakeholder is hypothetical. The business question
is where sessions leave the checkout funnel, how that varies by device/country,
and what an explicitly assumed recovery scenario might be worth.

| Metric | Definition |
|---|---|
| Session | Pair of user_pseudo_id and ga_session_id; both must be present |
| Session conversion | Sessions with a purchase divided by all sessions |
| Any-order funnel | Cumulative presence of each required event somewhere in a session |
| Strict ordered funnel | Cumulative events in strictly increasing timestamp order; ties do not prove order |
| Revenue | Purchase-event USD revenue; item revenue is reconciled separately |
| Observed new-user cohort | A user's first_visit appears within the full sample window, including sessionless first_visit evidence |
| Complement cohort | No observed first_visit; not confirmed returning |
| Channel | User first-touch traffic_source because stable session-level source/medium is absent in this sample |

Sessions crossing midnight are assigned once to their first observed export date.
The intermediate session model retains full loaded history and retrospectively
applies observed first_visit evidence. Incremental marts replace complete affected
start-date partitions; they retain unaffected sessions sharing those partitions.
A run includes its day, the previous day, and earlier affected session/cohort dates.

Drop-off opportunity is a modeled exposure: lost sessions multiplied by the next
step's observed continuer purchase behavior and purchase-event revenue. Recovery
scenarios assume 5%, 10%, or 20% of those losses can be recovered at that behavior.
Exact rational inputs are saved; scenario USD is floored to cents. These are not
causal lift, lost sales, forecasts, annualized estimates, or profit.

Product/category session counts overlap. Category reach is deduplicated directly
by category and the two-field session key; it can involve different products.
The observed item/category-key view/purchase matching gap limits interpretation.
Purchase-event revenue remains canonical when item revenue does not fully agree.

Source field inspection is in [schema.md](../reports/schema.md), analytical
findings in [funnel_global.md](../reports/funnel_global.md) and
[products.md](../reports/products.md), and incremental semantics in
[replay_design.md](replay_design.md). Original query IDs/results and all exact
inputs remain in [metrics.json](../reports/metrics.json).

## Dataset and scope limitations

LIMIT: hypothetical stakeholder; portfolio project on public data; no real deployment or users

LIMIT: obfuscated sample data; some totals don't fully reconcile

LIMIT: channel results are first-touch unless session-level source exists in the data

LIMIT: the daily pipeline replays historical daily tables as a simulated feed
