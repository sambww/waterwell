#!/usr/bin/env python3
"""
Customer Deduplication Tool for Ballard Water Well

Identifies potential duplicate customers from QuickBooks/Workiz exports
using fuzzy matching on names, phone numbers, and addresses.

Usage:
    python dedup.py customers.csv
    python dedup.py customers.csv --threshold 70 --output duplicates.csv
"""

import argparse
import csv
import re
import sys
from collections import defaultdict
from dataclasses import dataclass
from difflib import SequenceMatcher
from pathlib import Path
from typing import Optional


@dataclass
class Customer:
    id: str
    name: str
    phone: str
    email: str
    address: str
    city: str
    state: str
    zip_code: str
    source: str = ""

    @property
    def normalized_name(self) -> str:
        return normalize_name(self.name)

    @property
    def normalized_phone(self) -> str:
        return normalize_phone(self.phone)

    @property
    def normalized_address(self) -> str:
        return normalize_address(self.address)


@dataclass
class DuplicatePair:
    customer1: Customer
    customer2: Customer
    score: float
    reasons: list[str]

    def __lt__(self, other):
        return self.score > other.score  # Higher scores first


def normalize_name(name: str) -> str:
    """Normalize name for comparison."""
    if not name:
        return ""
    name = name.lower().strip()
    name = re.sub(r'[^\w\s]', '', name)
    name = re.sub(r'\s+', ' ', name)

    # Common name variations
    replacements = {
        'william': 'bill',
        'robert': 'bob',
        'richard': 'rick',
        'michael': 'mike',
        'james': 'jim',
        'samuel': 'sam',
        'elizabeth': 'liz',
        'jennifer': 'jen',
        'katherine': 'kate',
        'patricia': 'pat',
        'margaret': 'marge',
        'joseph': 'joe',
        'anthony': 'tony',
        'christopher': 'chris',
        'daniel': 'dan',
        'matthew': 'matt',
        'timothy': 'tim',
        'steven': 'steve',
        'thomas': 'tom',
        'andrew': 'andy',
    }

    words = name.split()
    normalized_words = []
    for word in words:
        normalized_words.append(replacements.get(word, word))

    return ' '.join(normalized_words)


def normalize_phone(phone: str) -> str:
    """Extract just digits from phone number."""
    if not phone:
        return ""
    digits = re.sub(r'\D', '', phone)
    # Handle US numbers with country code
    if len(digits) == 11 and digits.startswith('1'):
        digits = digits[1:]
    return digits


def normalize_address(address: str) -> str:
    """Normalize address for comparison."""
    if not address:
        return ""
    address = address.lower().strip()

    # Standard abbreviations
    replacements = {
        'street': 'st',
        'avenue': 'ave',
        'boulevard': 'blvd',
        'drive': 'dr',
        'lane': 'ln',
        'road': 'rd',
        'court': 'ct',
        'circle': 'cir',
        'place': 'pl',
        'highway': 'hwy',
        'county road': 'cr',
        'county rd': 'cr',
        'farm road': 'fm',
        'farm to market': 'fm',
        'ranch road': 'rr',
        'north': 'n',
        'south': 's',
        'east': 'e',
        'west': 'w',
        'apartment': 'apt',
        'suite': 'ste',
        'building': 'bldg',
        'number': '#',
    }

    for full, abbrev in replacements.items():
        address = re.sub(rf'\b{full}\b', abbrev, address)

    address = re.sub(r'[^\w\s#]', '', address)
    address = re.sub(r'\s+', ' ', address)

    return address


def levenshtein_ratio(s1: str, s2: str) -> float:
    """Calculate similarity ratio between two strings (0-100)."""
    if not s1 or not s2:
        return 0.0
    return SequenceMatcher(None, s1, s2).ratio() * 100


def phone_match_score(phone1: str, phone2: str) -> float:
    """Score phone number match (0-100)."""
    p1 = normalize_phone(phone1)
    p2 = normalize_phone(phone2)

    if not p1 or not p2:
        return 0.0

    if p1 == p2:
        return 100.0

    # Check if one is a suffix of the other (partial match)
    if len(p1) >= 7 and len(p2) >= 7:
        if p1[-7:] == p2[-7:]:
            return 80.0
        if p1[-10:] == p2[-10:] or p2[-10:] == p1[-10:]:
            return 90.0

    return 0.0


def name_match_score(name1: str, name2: str) -> float:
    """Score name similarity (0-100)."""
    n1 = normalize_name(name1)
    n2 = normalize_name(name2)

    if not n1 or not n2:
        return 0.0

    if n1 == n2:
        return 100.0

    # Check for initial matches (e.g., "S. Ballard" vs "Sam Ballard")
    words1 = n1.split()
    words2 = n2.split()

    # Last name match with first initial
    if len(words1) >= 2 and len(words2) >= 2:
        if words1[-1] == words2[-1]:  # Same last name
            # Check if first name is initial
            if len(words1[0]) == 1 and words2[0].startswith(words1[0]):
                return 90.0
            if len(words2[0]) == 1 and words1[0].startswith(words2[0]):
                return 90.0

    return levenshtein_ratio(n1, n2)


def address_match_score(addr1: str, city1: str, zip1: str,
                        addr2: str, city2: str, zip2: str) -> float:
    """Score address similarity (0-100)."""
    # Zip code match is strong signal
    z1 = normalize_phone(zip1)[:5] if zip1 else ""
    z2 = normalize_phone(zip2)[:5] if zip2 else ""

    zip_match = z1 == z2 if z1 and z2 else False

    a1 = normalize_address(addr1)
    a2 = normalize_address(addr2)

    if not a1 or not a2:
        if zip_match:
            return 50.0
        return 0.0

    addr_ratio = levenshtein_ratio(a1, a2)

    if zip_match:
        return min(100.0, addr_ratio + 20.0)

    return addr_ratio


def calculate_duplicate_score(c1: Customer, c2: Customer) -> tuple[float, list[str]]:
    """
    Calculate overall duplicate probability score (0-100).
    Returns (score, list of match reasons).
    """
    reasons = []
    scores = []
    weights = []

    # Phone match (highest weight - phone is most unique)
    phone_score = phone_match_score(c1.phone, c2.phone)
    if phone_score >= 80:
        reasons.append(f"Phone match: {phone_score:.0f}%")
        scores.append(phone_score)
        weights.append(3.0)

    # Name match
    name_score = name_match_score(c1.name, c2.name)
    if name_score >= 70:
        reasons.append(f"Name match: {name_score:.0f}%")
        scores.append(name_score)
        weights.append(2.0)

    # Address match
    addr_score = address_match_score(
        c1.address, c1.city, c1.zip_code,
        c2.address, c2.city, c2.zip_code
    )
    if addr_score >= 60:
        reasons.append(f"Address match: {addr_score:.0f}%")
        scores.append(addr_score)
        weights.append(1.5)

    # Email match
    if c1.email and c2.email:
        e1 = c1.email.lower().strip()
        e2 = c2.email.lower().strip()
        if e1 == e2:
            reasons.append("Email exact match")
            scores.append(100.0)
            weights.append(2.5)

    if not scores:
        return 0.0, []

    # Weighted average
    total_weight = sum(weights)
    weighted_score = sum(s * w for s, w in zip(scores, weights)) / total_weight

    # Bonus for multiple strong matches
    strong_matches = sum(1 for s in scores if s >= 80)
    if strong_matches >= 2:
        weighted_score = min(100.0, weighted_score + 10.0)
        reasons.append(f"{strong_matches} strong matches")

    return weighted_score, reasons


def find_duplicates(customers: list[Customer], threshold: float = 70.0) -> list[DuplicatePair]:
    """Find all potential duplicate pairs above threshold."""
    duplicates = []
    n = len(customers)

    # Build phone index for faster lookups
    phone_index = defaultdict(list)
    for c in customers:
        phone = normalize_phone(c.phone)
        if phone:
            phone_index[phone].append(c)
            # Also index last 7 digits
            if len(phone) >= 7:
                phone_index[phone[-7:]].append(c)

    # Compare all pairs
    for i in range(n):
        for j in range(i + 1, n):
            c1, c2 = customers[i], customers[j]
            score, reasons = calculate_duplicate_score(c1, c2)
            if score >= threshold:
                duplicates.append(DuplicatePair(c1, c2, score, reasons))

    return sorted(duplicates)


def load_customers(csv_path: str) -> list[Customer]:
    """Load customers from CSV file."""
    customers = []

    # Map common column name variations
    column_map = {
        'id': ['id', 'customer_id', 'customerid', 'client_id', 'clientid', 'qb_id', 'quickbooks_id'],
        'name': ['name', 'customer_name', 'client_name', 'display_name', 'displayname', 'full_name', 'fullname', 'customer'],
        'phone': ['phone', 'phone_number', 'phonenumber', 'mobile', 'telephone', 'cell', 'primary_phone'],
        'email': ['email', 'email_address', 'emailaddress', 'e_mail'],
        'address': ['address', 'street', 'street_address', 'billing_address', 'billingaddress', 'address1', 'line1'],
        'city': ['city', 'billing_city', 'billingcity'],
        'state': ['state', 'billing_state', 'billingstate', 'province'],
        'zip': ['zip', 'zip_code', 'zipcode', 'postal', 'postal_code', 'postalcode', 'billing_zip'],
        'source': ['source', 'origin', 'created_by', 'system'],
    }

    with open(csv_path, 'r', encoding='utf-8-sig') as f:
        reader = csv.DictReader(f)
        headers = {h.lower().strip(): h for h in reader.fieldnames or []}

        # Find actual column names
        actual_cols = {}
        for field, variations in column_map.items():
            for var in variations:
                if var in headers:
                    actual_cols[field] = headers[var]
                    break

        row_num = 0
        for row in reader:
            row_num += 1
            customers.append(Customer(
                id=row.get(actual_cols.get('id', ''), str(row_num)),
                name=row.get(actual_cols.get('name', ''), ''),
                phone=row.get(actual_cols.get('phone', ''), ''),
                email=row.get(actual_cols.get('email', ''), ''),
                address=row.get(actual_cols.get('address', ''), ''),
                city=row.get(actual_cols.get('city', ''), ''),
                state=row.get(actual_cols.get('state', ''), ''),
                zip_code=row.get(actual_cols.get('zip', ''), ''),
                source=row.get(actual_cols.get('source', ''), ''),
            ))

    return customers


def generate_report(duplicates: list[DuplicatePair], output_format: str = 'text') -> str:
    """Generate duplicate report."""
    if not duplicates:
        return "No potential duplicates found above threshold."

    lines = []
    lines.append("=" * 80)
    lines.append("CUSTOMER DUPLICATE REPORT")
    lines.append(f"Found {len(duplicates)} potential duplicate pairs")
    lines.append("=" * 80)
    lines.append("")

    for i, dup in enumerate(duplicates, 1):
        lines.append(f"#{i} - Match Score: {dup.score:.1f}%")
        lines.append("-" * 40)

        lines.append(f"  Customer A (ID: {dup.customer1.id}):")
        lines.append(f"    Name:    {dup.customer1.name}")
        lines.append(f"    Phone:   {dup.customer1.phone}")
        lines.append(f"    Email:   {dup.customer1.email}")
        lines.append(f"    Address: {dup.customer1.address}")
        lines.append(f"    City:    {dup.customer1.city}, {dup.customer1.state} {dup.customer1.zip_code}")
        if dup.customer1.source:
            lines.append(f"    Source:  {dup.customer1.source}")

        lines.append("")
        lines.append(f"  Customer B (ID: {dup.customer2.id}):")
        lines.append(f"    Name:    {dup.customer2.name}")
        lines.append(f"    Phone:   {dup.customer2.phone}")
        lines.append(f"    Email:   {dup.customer2.email}")
        lines.append(f"    Address: {dup.customer2.address}")
        lines.append(f"    City:    {dup.customer2.city}, {dup.customer2.state} {dup.customer2.zip_code}")
        if dup.customer2.source:
            lines.append(f"    Source:  {dup.customer2.source}")

        lines.append("")
        lines.append("  Match Reasons:")
        for reason in dup.reasons:
            lines.append(f"    - {reason}")

        lines.append("")
        lines.append("  ACTION: Review and merge in QuickBooks if confirmed duplicate")
        lines.append("  QB Merge: Sales > Customers > Select both > Batch Actions > Merge")
        lines.append("")

    return '\n'.join(lines)


def export_csv(duplicates: list[DuplicatePair], output_path: str):
    """Export duplicates to CSV for easy review."""
    with open(output_path, 'w', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        writer.writerow([
            'Match Score', 'Reasons',
            'ID_A', 'Name_A', 'Phone_A', 'Email_A', 'Address_A', 'City_A', 'Source_A',
            'ID_B', 'Name_B', 'Phone_B', 'Email_B', 'Address_B', 'City_B', 'Source_B',
        ])

        for dup in duplicates:
            writer.writerow([
                f"{dup.score:.1f}%",
                '; '.join(dup.reasons),
                dup.customer1.id, dup.customer1.name, dup.customer1.phone,
                dup.customer1.email, dup.customer1.address, dup.customer1.city,
                dup.customer1.source,
                dup.customer2.id, dup.customer2.name, dup.customer2.phone,
                dup.customer2.email, dup.customer2.address, dup.customer2.city,
                dup.customer2.source,
            ])


def main():
    parser = argparse.ArgumentParser(
        description='Find duplicate customers in QuickBooks/Workiz exports'
    )
    parser.add_argument('input', help='Input CSV file with customer data')
    parser.add_argument('--threshold', '-t', type=float, default=70.0,
                        help='Minimum match score to report (0-100, default: 70)')
    parser.add_argument('--output', '-o', help='Output CSV file for results')
    parser.add_argument('--quiet', '-q', action='store_true',
                        help='Only output CSV, no text report')

    args = parser.parse_args()

    if not Path(args.input).exists():
        print(f"Error: Input file not found: {args.input}", file=sys.stderr)
        sys.exit(1)

    print(f"Loading customers from {args.input}...", file=sys.stderr)
    customers = load_customers(args.input)
    print(f"Loaded {len(customers)} customers", file=sys.stderr)

    print(f"Analyzing for duplicates (threshold: {args.threshold}%)...", file=sys.stderr)
    duplicates = find_duplicates(customers, args.threshold)
    print(f"Found {len(duplicates)} potential duplicate pairs", file=sys.stderr)

    if not args.quiet:
        print()
        print(generate_report(duplicates))

    if args.output:
        export_csv(duplicates, args.output)
        print(f"\nResults exported to: {args.output}", file=sys.stderr)


if __name__ == '__main__':
    main()
