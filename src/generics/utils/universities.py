import os
import csv

from src import RESOURCES_PATH


UNIVERSITY_DATA_FILE = os.path.join(RESOURCES_PATH, "universities.csv")


def universities():
    """
    Load and yield universities data from a CSV file.
    """
    with open(UNIVERSITY_DATA_FILE, "r", encoding="utf-8") as file:
        reader = csv.DictReader(file)
        for row in reader:
            yield dict(row.items())


def universities_by_country():
    """
    Loads and returns universities data grouped by country from a CSV file.
    """
    _universities = {}
    for university in universities():
        country = university["country"].strip().upper()
        if country not in _universities:
            _universities[country] = []

        university.pop("country")
        _universities[country].append(university)
    return _universities


def university_names():
    """
    Load and yield university names from a CSV file.
    """
    for university in universities():
        yield university["name"].strip()


def university_names_by_country():
    """
    Load and returns university names grouped by country from a CSV file.
    """
    _universities = {}
    for university in universities():
        country = university["country"].strip().upper()
        if country not in _universities:
            _universities[country] = []

        _universities[country].append(university["name"].strip())
    return _universities
