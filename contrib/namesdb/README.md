# Name mapping database project

This is a nascent effort to provide a QA layer for name mappings that are eventually going to be used by rigour.

## Cleanup

```sql
UPDATE mapping SET skip = true WHERE form LIKE '%family name%';
UPDATE mapping SET skip = true WHERE form LIKE '%surname%';
UPDATE mapping SET skip = true WHERE form LIKE '%given name%';
UPDATE mapping SET skip = true WHERE form LIKE '%male name%';
UPDATE mapping SET skip = true WHERE form LIKE '%son of%';
UPDATE mapping SET skip = true WHERE form LIKE '%head of%';
UPDATE mapping SET skip = true WHERE form LIKE '%adelsgeschlecht%';
UPDATE mapping SET skip = true WHERE form LIKE '%cap de la casa%';
```

SELECT form, COUNT(*) FROM mapping GROUP BY form ORDER BY COUNT(*) DESC LIMIT 50;