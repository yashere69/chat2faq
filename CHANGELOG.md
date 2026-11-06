# Changelog

## 0.2.0

- Day/month order detected per file (US-locale exports crashed before); `--date-order` to force it
- Media, deletion and missed-call placeholders skipped; edit markers stripped
- Labels can name a file, for folders of per-customer exports
- `--business` checked against the export; a guessed store name is announced
- Pairing and grouping made linear-ish (21k lines: ~30 s to ~2.5 s)
- Sample data is now a folder of per-customer exports

## 0.1.0

- Android and iOS export parsing (12/24-hour, U+202F, multi-line messages)
- Redaction via parda when installed, built-in patterns otherwise
- Question detection, reply pairing, char n-gram grouping, answer-side merging
- Lookup detection for order-specific answers
- Markdown and JSONL output; `--labels` evaluation
