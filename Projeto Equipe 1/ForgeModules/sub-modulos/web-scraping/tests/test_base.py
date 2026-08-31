"""Testes da interface de fontes de dados."""

from collector.base import AcademicDataSource
from collector.open_meteo import OpenMeteoSource
from collector.university_api import UniversityApiSource
from collector.university_portal import UniversityPortalScraper


def test_open_meteo_implements_interface() -> None:
    source = OpenMeteoSource("https://api.open-meteo.com/v1", "Open-Meteo")
    assert isinstance(source, AcademicDataSource)
    assert source.source_type == "api"


def test_university_stubs_implement_interface() -> None:
    api = UniversityApiSource("https://portal.university.edu/api")
    portal = UniversityPortalScraper("https://portal.edu", "user", "pass")
    assert isinstance(api, AcademicDataSource)
    assert isinstance(portal, AcademicDataSource)
    assert portal.source_type == "portal"
