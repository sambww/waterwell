# Customer Deduplication Skill

Identifies duplicate customers created by Workiz AI phone answering that sync 
to QuickBooks. Finds matches like "Sam Ballard" vs "Samuel Ballard" vs "S. Ballard"
using fuzzy matching on names, phone numbers, and addresses.

## Quick Start

```bash
# Export customers from QuickBooks via Zapier or direct export
# Run the dedup tool
python3 skills/customer-dedup/dedup.py customers.csv

# With custom threshold and CSV output
python3 skills/customer-dedup/dedup.py customers.csv --threshold 60 --output duplicates.csv
```

## How It Works

The tool uses multiple matching strategies:

| Field | Weight | Method |
|-------|--------|--------|
| Phone | 3.0x | Exact match + partial (last 7-10 digits) |
| Name | 2.0x | Levenshtein + nickname normalization |
| Email | 2.5x | Exact match |
| Address | 1.5x | Normalized + zip code bonus |

**Nickname normalization** handles:
- Samuel → Sam, William → Bill, Robert → Bob, etc.
- First initial matches: "S. Ballard" matches "Sam Ballard"

**Address normalization** handles:
- Street → St, Avenue → Ave, County Road → CR
- Directional abbreviations: North → N, South → S

## Input CSV Format

The tool auto-detects common column names. Any of these work:

| Required | Accepted Column Names |
|----------|----------------------|
| Name | `name`, `customer_name`, `display_name`, `full_name` |
| Phone | `phone`, `phone_number`, `mobile`, `telephone` |
| Email | `email`, `email_address` |
| Address | `address`, `street`, `billing_address` |
| City | `city`, `billing_city` |
| State | `state`, `billing_state` |
| Zip | `zip`, `zip_code`, `postal_code` |

### Sample CSV

```csv
id,name,phone,email,address,city,state,zip
1,Samuel Ballard,512-555-1234,sam@example.com,123 Main St,Austin,TX,78701
2,Sam Ballard,(512) 555-1234,samuel@example.com,123 Main Street,Austin,TX,78701
3,S. Ballard,5125551234,,123 Main,Austin,TX,78701
```

## Output

### Text Report (stdout)

```
================================================================================
CUSTOMER DUPLICATE REPORT
Found 1 potential duplicate pairs
================================================================================

#1 - Match Score: 95.2%
----------------------------------------
  Customer A (ID: 1):
    Name:    Samuel Ballard
    Phone:   512-555-1234
    Email:   sam@example.com
    Address: 123 Main St
    City:    Austin, TX 78701

  Customer B (ID: 2):
    Name:    Sam Ballard
    Phone:   (512) 555-1234
    Email:   samuel@example.com
    Address: 123 Main Street
    City:    Austin, TX 78701

  Match Reasons:
    - Phone match: 100%
    - Name match: 100%
    - Address match: 95%
    - 3 strong matches

  ACTION: Review and merge in QuickBooks if confirmed duplicate
  QB Merge: Sales > Customers > Select both > Batch Actions > Merge
```

### CSV Export (--output)

Use `--output duplicates.csv` to get a spreadsheet for Angie/Pam to review.

## Command Line Options

| Option | Description |
|--------|-------------|
| `--threshold`, `-t` | Minimum match score (0-100, default: 70) |
| `--output`, `-o` | Export results to CSV file |
| `--quiet`, `-q` | Suppress text report, only output CSV |

## Integration with Zapier

1. Create a Zap: QuickBooks → Export Customers to Google Sheets
2. Download the sheet as CSV
3. Run this tool on the CSV
4. Use the report to merge duplicates in QuickBooks

## Recommended Workflow

1. **Weekly audit**: Run dedup on full customer export
2. **Pre-sync validation**: Run dedup on new Workiz leads before QB sync
3. **Threshold tuning**: Start at 70%, lower to 60% if missing duplicates

## SOP for Office Staff

When duplicates are found:

1. Open QuickBooks Online
2. Go to Sales → Customers
3. Search for both customer names
4. Compare jobs, invoices, estimates on each
5. Keep the record with more history
6. Use Batch Actions → Merge to combine
7. If both have jobs: manually reassign before merge
