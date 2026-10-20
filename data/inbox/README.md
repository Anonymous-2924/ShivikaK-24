# data/inbox/

Drop files here. The app reads EXCLUSIVELY from this directory.

Empty on delivery. The standalone generator writes to `generated_data/`
(gitignored); move files from there into here manually.

Accepted file types (Phase 3 will route based on extension and content):

| Extension          | Track      | Notes                                      |
|--------------------|------------|--------------------------------------------|
| `.pdf`             | both       | prose → narrative; tables → numeric if confidence ≥ floor |
| `.docx`            | narrative  |                                            |
| `.txt`, `.md`      | narrative  |                                            |
| `.xlsx`, `.xls`    | numeric    | each sheet becomes its own parquet + card  |
| `.csv`, `.tsv`     | numeric    |                                            |
| `.json`, `.xml`    | numeric    | ERP-style structured exports               |
| `.png`, `.jpg`     | narrative  | chart/image OCR (optional)                 |
