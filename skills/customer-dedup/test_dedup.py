#!/usr/bin/env python3
"""Unit tests for customer deduplication logic."""

import unittest
from dedup import (
    normalize_name,
    normalize_phone,
    normalize_address,
    name_match_score,
    phone_match_score,
    address_match_score,
    Customer,
    calculate_duplicate_score,
)


class TestNormalization(unittest.TestCase):
    def test_normalize_name_basic(self):
        self.assertEqual(normalize_name("Samuel Ballard"), "sam ballard")
        self.assertEqual(normalize_name("SAMUEL BALLARD"), "sam ballard")
        self.assertEqual(normalize_name("  Samuel   Ballard  "), "sam ballard")

    def test_normalize_name_nicknames(self):
        self.assertEqual(normalize_name("William Smith"), "bill smith")
        self.assertEqual(normalize_name("Robert Johnson"), "bob johnson")
        self.assertEqual(normalize_name("Jennifer Martinez"), "jen martinez")
        self.assertEqual(normalize_name("Patricia Brown"), "pat brown")

    def test_normalize_phone(self):
        self.assertEqual(normalize_phone("512-555-1234"), "5125551234")
        self.assertEqual(normalize_phone("(512) 555-1234"), "5125551234")
        self.assertEqual(normalize_phone("1-512-555-1234"), "5125551234")
        self.assertEqual(normalize_phone("+1 512 555 1234"), "5125551234")

    def test_normalize_address(self):
        self.assertEqual(normalize_address("123 Main Street"), "123 main st")
        self.assertEqual(normalize_address("456 Oak Avenue"), "456 oak ave")
        self.assertEqual(normalize_address("789 County Road 100"), "789 cr 100")
        self.assertEqual(normalize_address("321 North Elm Drive"), "321 n elm dr")


class TestMatching(unittest.TestCase):
    def test_phone_exact_match(self):
        self.assertEqual(phone_match_score("512-555-1234", "5125551234"), 100.0)
        self.assertEqual(phone_match_score("(512) 555-1234", "512.555.1234"), 100.0)

    def test_phone_partial_match(self):
        score = phone_match_score("512-555-1234", "555-1234")
        self.assertGreaterEqual(score, 80.0)

    def test_phone_no_match(self):
        self.assertEqual(phone_match_score("512-555-1234", "512-555-4321"), 0.0)

    def test_name_exact_match(self):
        self.assertEqual(name_match_score("Samuel Ballard", "Sam Ballard"), 100.0)
        self.assertEqual(name_match_score("William Smith", "Bill Smith"), 100.0)

    def test_name_initial_match(self):
        score = name_match_score("S. Ballard", "Samuel Ballard")
        self.assertGreaterEqual(score, 90.0)

    def test_name_similar(self):
        score = name_match_score("Samuel Ballard", "Samual Ballard")
        self.assertGreaterEqual(score, 85.0)

    def test_address_match(self):
        score = address_match_score(
            "123 Main Street", "Austin", "78701",
            "123 Main St", "Austin", "78701"
        )
        self.assertGreaterEqual(score, 90.0)


class TestDuplicateDetection(unittest.TestCase):
    def test_obvious_duplicate(self):
        c1 = Customer(
            id="1", name="Samuel Ballard", phone="512-555-1234",
            email="sam@example.com", address="123 Main St",
            city="Austin", state="TX", zip_code="78701"
        )
        c2 = Customer(
            id="2", name="Sam Ballard", phone="(512) 555-1234",
            email="", address="123 Main Street",
            city="Austin", state="TX", zip_code="78701"
        )
        score, reasons = calculate_duplicate_score(c1, c2)
        self.assertGreaterEqual(score, 90.0)
        self.assertGreater(len(reasons), 0)

    def test_different_customers(self):
        c1 = Customer(
            id="1", name="John Smith", phone="512-555-1111",
            email="john@example.com", address="100 First St",
            city="Austin", state="TX", zip_code="78701"
        )
        c2 = Customer(
            id="2", name="Mary Jones", phone="512-555-2222",
            email="mary@example.com", address="200 Second St",
            city="Round Rock", state="TX", zip_code="78664"
        )
        score, reasons = calculate_duplicate_score(c1, c2)
        self.assertLess(score, 50.0)


if __name__ == '__main__':
    unittest.main()
