We need customers to export the monthly revenue report as CSV. It should respect their current filters, only admins should be able to export it, and we need analytics on usage.
Product decisions for this request:
Export at most 10,000 rows; if more rows match, reject the entire export with an actionable message and no partial file.
Use UTF-8 CSV with headers month, revenue, currency; exclude customer identifiers and other sensitive fields.
Use the existing report totals without recalculating financial amounts; preserve currency codes.
For the approved 10,000-row fixture, export completes within 5 seconds in the staging performance test.
Enforce administrator authorization on the server and hide the export action from non-admins.
Emit revenue_export_completed only after a successful export, with row_count and active_filter_names; omit filter values and customer identifiers.
Neutralize spreadsheet formula prefixes in every CSV cell.
Backend export, frontend action, authorization, analytics, and regression validation must have separate work items.
