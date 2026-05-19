# customer-dedup

Identify and report duplicate customers from QuickBooks/Workiz CSV exports.

## Trigger

Use this skill when the user:
- Asks to find duplicate customers
- Wants to clean up customer data from Workiz or QuickBooks
- Mentions "dedup", "deduplication", or "duplicate customers"
- Has a CSV of customers and wants to find redundant entries
- Mentions problems with Workiz AI phone answering creating duplicate records

## Instructions

1. **Get the input file**: Ask the user for a CSV file containing customer data (QuickBooks export, Workiz export, or any customer list). The CSV should have columns for name, phone, email, and/or address.

2. **Run the dedup tool**:
   ```bash
   python3 <skill_path>/dedup.py <input.csv>
   ```

3. **Options**:
   - `--threshold 60` - Lower threshold to catch more potential duplicates (default: 70)
   - `--output duplicates.csv` - Export results to CSV for office review
   - `--quiet` - Suppress text report, only output CSV

4. **Interpret results**: The tool outputs a ranked list of potential duplicate pairs with:
   - Match score (0-100%)
   - Match reasons (phone, name, address, email)
   - Recommended actions for QuickBooks merge

5. **Provide merge instructions**: For confirmed duplicates, guide the user through:
   - QuickBooks: Sales > Customers > Select both > Batch Actions > Merge
   - Keep the record with more history (jobs, invoices, estimates)

## Matching Logic

| Field | Weight | Method |
|-------|--------|--------|
| Phone | 3.0x | Exact match + partial (last 7-10 digits) |
| Name | 2.0x | Levenshtein + nickname normalization (Samuel=Sam, William=Bill) |
| Email | 2.5x | Exact match |
| Address | 1.5x | Normalized street types + zip code bonus |

## Example

```bash
# Basic scan
python3 <skill_path>/dedup.py customers.csv

# Catch more duplicates with lower threshold
python3 <skill_path>/dedup.py customers.csv --threshold 60 --output cleanup_list.csv
```

## Dependencies

- Python 3.8+
- No external packages required (uses only standard library)
